const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
const ts=require('typescript');const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');
function load(file,imports){const module={exports:{}};const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,esModuleInterop:true}}).outputText;vm.runInNewContext(code,{module,exports:module.exports,require:name=>Object.hasOwn(imports,name)?imports[name]:require(name)});return module.exports;}
const design=load('components/dashboard/moderation-design.tsx',{'@/lib/utils':{cn:(...items)=>items.filter(Boolean).join(' ')}});
function jail(draft){const picker=props=>React.createElement('input',{'data-picker':props.placeholder,value:props.value,readOnly:true});const data={configured:true,inmates:[],jail_role:{id:'111'},jail_channel:{id:'222'},mod_role:{id:'333'},log_channel:null};const panels=load('components/dashboard/extras-panels.tsx',{
 '@/components/dashboard/moderation-design':design,'@/components/ui/website-select':{},'@/components/dashboard/pickers':{ChannelPicker:picker,RolePicker:picker},'@/components/dashboard/user-picker':{},'@/components/dashboard/emoji-picker':{},'@/components/dashboard/discord-emoji':{},'@/components/dashboard/form-elements':{},'@/lib/api':{api:{}},'@/lib/utils':{cn:(...items)=>items.filter(Boolean).join(' ')},'@/components/dashboard/save-bar':{usePanel:()=>({data,draft,reload:()=>{},loading:false,busy:false,dirty:Object.keys(draft).length,value:key=>Object.hasOwn(draft,key)?draft[key]:data[key]}),useSaveGuard:()=>({shake:false}),StickySaveBar:()=>null},
});return renderToStaticMarkup(React.createElement(panels.JailPanel,{guildId:'1'}));}
test('Jail keeps newly selected string IDs visible alongside saved object IDs',()=>{
 const html=jail({jail_role:'1557183988672766043',log_channel:'1530378233579704370'});
 assert.match(html,/value="1557183988672766043"/);assert.match(html,/value="1530378233579704370"/);assert.match(html,/value="222"/);assert.match(html,/value="333"/);
});
test('refresh is disabled while Jail edits are unsaved',()=>{assert.match(jail({mod_role:'444'}),/disabled=""/);assert.doesNotMatch(jail({}),/disabled=""/);});
