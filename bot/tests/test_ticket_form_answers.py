"""Real checkbox groups and a single form card with quoted answers and uploads."""
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discord
from cogs.commands.ticket_workflow import add_fields, form_answers, send_answers
from utils import ticket_settings


class FormAnswerTests(unittest.IsolatedAsyncioTestCase):
    def attachment(self, name, content_type):
        return NS(filename=name, content_type=content_type, url=f'https://cdn.discordapp.com/attachments/1/2/{name}',
                  to_file=AsyncMock(side_effect=lambda: discord.File(io.BytesIO(b'example'), filename=name)))

    async def test_checkbox_options_are_separate_from_heading_and_allow_multiple_answers(self):
        question={'label':'What do you need?', 'type':'checkbox', 'options':['Premium','Account','Other'], 'required':True}
        clean=ticket_settings.validate({'opening_questions':[question]})['opening_questions'][0]
        modal=discord.ui.Modal(title='Opening form')
        inputs=add_fields(modal,[clean])
        group=inputs[0][1]
        self.assertIsInstance(group,discord.ui.CheckboxGroup)
        self.assertEqual(modal.children[0].text,'What do you need?')
        self.assertEqual([option.label for option in group.options],['Premium','Account','Other'])
        self.assertEqual(group.max_values,3);self.assertEqual(group.min_values,1)
        group._values=['0','2']
        self.assertEqual(form_answers(inputs)[0]['value'],'Premium\nOther')
        group._values=[]
        with self.assertRaises(ValueError):form_answers(inputs)

    async def test_optional_checkbox_and_legacy_confirmation_remain_supported(self):
        modal=discord.ui.Modal(title='Opening form')
        inputs=add_fields(modal,[{'label':'Extras','type':'checkbox','options':['A'],'required':False},
                                 {'label':'Legacy consent','type':'checkbox','required':False}])
        self.assertEqual(form_answers(inputs)[0]['value'],'')
        self.assertIsInstance(inputs[1][1],discord.ui.Checkbox)
        self.assertEqual(form_answers(inputs)[1]['value'],'No')
        with self.assertRaises(ValueError):
            ticket_settings.validate({'closing_questions':[{'label':'Too many','type':'checkbox','options':[str(n) for n in range(11)]}]})

    async def test_one_card_quotes_text_and_places_image_and_file_directly_after_questions(self):
        channel=NS(send=AsyncMock())
        await send_answers(channel,'Opening form',[
            {'label':'Open reason','type':'paragraph','value':'Need help\nWith Premium'},
            {'label':'Screenshot','type':'image','attachments':[self.attachment('evidence.png','image/png')]},
            {'label':'Document','type':'file','attachments':[self.attachment('proof.pdf','application/pdf')]},
            {'label':'Count','type':'short','value':0}])
        channel.send.assert_awaited_once()
        kwargs=channel.send.call_args.kwargs
        self.assertIsInstance(kwargs['view'],discord.ui.LayoutView)
        components=kwargs['view'].to_components()[0]['components']
        text='\n'.join(item['content'] for item in components if item['type']==10)
        self.assertIn('**Open reason**\n> Need help\n> With Premium',text)
        self.assertIn('**Count**\n> 0',text)
        self.assertNotIn('No answer',text);self.assertNotIn('Not provided',text)
        image_index=next(i for i,item in enumerate(components) if item.get('content')=='**Screenshot**')
        self.assertEqual(components[image_index+1]['type'],12)
        self.assertIn('attachment://question-2-1-evidence.png',str(components[image_index+1]))
        file_index=next(i for i,item in enumerate(components) if item.get('content')=='**Document**')
        self.assertEqual(components[file_index+1]['type'],13)
        self.assertEqual(len(kwargs['files']),2)
        self.assertEqual(kwargs['allowed_mentions'].to_dict()['parse'],[])

    async def test_failed_image_download_still_renders_existing_attachment_url(self):
        picture=self.attachment('photo.png','image/png')
        picture.to_file.side_effect=discord.HTTPException(NS(status=503,reason='Unavailable'),'download failed')
        channel=NS(send=AsyncMock())
        await send_answers(channel,'Opening form',[{'label':'Evidence','type':'image','attachments':[picture]}])
        payload=str(channel.send.call_args.kwargs['view'].to_components())
        self.assertIn(picture.url,payload);self.assertNotIn('No answer',payload)
        self.assertNotIn('files',channel.send.call_args.kwargs)

    async def test_long_answers_fit_one_message_and_full_text_is_preserved(self):
        saved={}
        async def capture(**kwargs):
            saved.update(kwargs)
            saved['full_text']=kwargs['files'][-1].fp.read().decode('utf-8')
        channel=NS(send=AsyncMock(side_effect=capture))
        answers=[{'label':f'Question {n}','type':'paragraph','value':f'Answer {n}: '+'abcdefghij\n'*350} for n in range(5)]
        await send_answers(channel,'Opening form',answers)
        channel.send.assert_awaited_once()
        self.assertLessEqual(saved['view'].content_length(),4000)
        for answer in answers:
            self.assertIn('**'+answer['label']+'**',str(saved['view'].to_components()))
            self.assertIn('\n'.join('> '+line for line in answer['value'].splitlines()),saved['full_text'])
        self.assertIn('attachment://full-form-answers.txt',str(saved['view'].to_components()))

    async def test_many_uploaded_images_stay_under_discord_limits_and_all_render(self):
        channel=NS(send=AsyncMock())
        answers=[{'label':f'Images {n}','type':'image','attachments':[self.attachment(f'{n}-{i}.png','image/png') for i in range(5)]} for n in range(5)]
        await send_answers(channel,'Opening form',answers)
        kwargs=channel.send.call_args.kwargs
        self.assertLessEqual(len(kwargs['files']),10)
        self.assertLessEqual(len(list(kwargs['view'].walk_children())),40)
        components=kwargs['view'].to_components()[0]['components']
        self.assertEqual(sum(len(item['items']) for item in components if item['type']==12),25)
        self.assertNotIn('No answer',str(components))


if __name__=='__main__':unittest.main()
