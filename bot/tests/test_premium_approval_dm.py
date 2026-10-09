"""Real Premium approvals notify only their recipient and keep grants on DM failure."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import discord
import httpx
from fastapi import FastAPI
from api.dependencies import get_bot
from api.routes import premium
from utils import premium_membership, premium_notice, premium_notifications, dm_preferences


class ApprovalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(premium_membership,'DB_PATH',self.temp.name+'/premium.db'),
                      patch.object(dm_preferences,'DB_PATH',self.temp.name+'/dm.db'),
                      patch.object(premium_notice,'zuruecksetzen'),
                      patch.object(premium_notifications,'dashboard_url',return_value='https://bot.example'),
                      patch.object(premium_notifications,'support_url',return_value='https://discord.gg/support')]
        for p in self.patches:p.start()
        self.user=NS(id=100,send=AsyncMock())
        self.bot=NS(get_user=Mock(return_value=self.user),fetch_user=AsyncMock(return_value=self.user))
        app=FastAPI();app.include_router(premium.router,prefix='/premium');app.dependency_overrides[get_bot]=lambda:self.bot
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test')
    async def asyncTearDown(self):
        await self.client.aclose()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    async def decide(self,approved=True):
        request=premium_membership.request_purchase(100,30)
        return request,await self.client.post(f"/premium/requests/{request['id']}/decide",json={'approve':approved,'actor':'999'})

    async def test_approval_sends_english_v2_with_emojis_link_and_no_repeat(self):
        request,response=await self.decide()
        self.assertEqual(response.status_code,200);self.assertTrue(response.json()['dm_sent'])
        self.bot.get_user.assert_called_once_with(100);self.bot.fetch_user.assert_not_awaited()
        kwargs=self.user.send.call_args.kwargs
        self.assertIsInstance(kwargs['view'],discord.ui.LayoutView);self.assertNotIn('content',kwargs)
        payload=str(kwargs['view'].to_components())
        self.assertIn('Premium approved',payload);self.assertIn('<:',payload);self.assertIn('> ',payload)
        self.assertIn('https://bot.example/dashboard/premium',payload)
        self.assertIn(str(response.json()['result']['expires_at']),payload)
        self.assertEqual(kwargs['allowed_mentions'].to_dict()['parse'],[])
        repeated=await self.client.post(f"/premium/requests/{request['id']}/decide",json={'approve':True})
        self.assertEqual(repeated.status_code,400);self.user.send.assert_awaited_once()

    async def test_selected_german_and_uncached_user_are_supported(self):
        dm_preferences.select(100,'de');self.bot.get_user.return_value=None
        _,response=await self.decide()
        self.assertTrue(response.json()['dm_sent']);self.bot.fetch_user.assert_awaited_once_with(100)
        payload=str(self.user.send.call_args.kwargs['view'].to_components())
        self.assertIn('Premium genehmigt',payload);self.assertIn('Premium verwalten',payload);self.assertNotIn('Premium approved',payload)

    async def test_blocked_dm_does_not_undo_premium(self):
        self.user.send.side_effect=discord.Forbidden(NS(status=403,reason='Forbidden'),'DMs closed')
        _,response=await self.decide()
        self.assertEqual(response.status_code,200);self.assertFalse(response.json()['dm_sent'])
        self.assertTrue(premium_membership.account_status(100)['premium'])

    async def test_denial_never_sends_approval_dm(self):
        _,response=await self.decide(False)
        self.assertEqual(response.status_code,200);self.assertIsNone(response.json()['dm_sent'])
        self.user.send.assert_not_awaited();self.assertFalse(premium_membership.account_status(100)['premium'])

    async def test_lifetime_approval_dm_has_no_synthetic_expiry_date(self):
        request=premium_membership.request_purchase(100,0)
        response=await self.client.post(f"/premium/requests/{request['id']}/decide",json={'approve':True,'actor':'999'})
        self.assertEqual(response.status_code,200);self.assertTrue(response.json()['dm_sent'])
        self.assertTrue(response.json()['result']['lifetime'])
        payload=str(self.user.send.call_args.kwargs['view'].to_components())
        self.assertIn('Lifetime',payload)
        self.assertNotIn(str(premium_membership.LIFETIME_EXPIRES_AT),payload)


if __name__=='__main__':unittest.main()
