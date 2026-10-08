const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const ts=require('typescript');const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');
function editor(){
  let props;const calls=[];
  const stored={leave_channel_id:'1557183988672766043',leave_type:'embed',leave_message:'Goodbye',leave_embed_data:{title:'Bye',footer_text:'Our server'},leave_auto_delete_duration:60,leave_image_enabled:true,leave_image_url:'https://example.org/bg.png'};
  const imports={react:React,'@/lib/api':{api:{saveGreetExtras:async(g,data)=>calls.push(['save',g,data]),testLeave:async(g,data)=>calls.push(['test',g,data])}},'@/components/dashboard/save-bar':{usePanel:()=>({data:stored,loading:false})},'@/components/dashboard/welcome-form':{WelcomeForm:value=>{props=value;return React.createElement('span',{},'Editor');}}};
  const module={exports:{}};
  const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../components/dashboard/leave-form.tsx'),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,esModuleInterop:true}}).outputText;
  vm.runInNewContext(code,{React,module,exports:module.exports,require:name=>Object.hasOwn(imports,name)?imports[name]:require(name)});
  renderToStaticMarkup(React.createElement(module.exports.LeaveForm,{guildId:'42'}));return{props,calls};
}
test('departure uses the complete greeting editor with the exact saved channel',()=>{
 const {props}=editor();assert.equal(props.kind,'leave');assert.equal(props.initialConfig.channel_id,'1557183988672766043');assert.equal(props.initialConfig.embed_data.footer_text,'Our server');assert.equal(props.initialConfig.auto_delete_duration,60);
});
test('departure save and preview carry the same complete settings without changing welcome or module state',async()=>{
 const {props,calls}=editor();const config={...props.initialConfig,channel_id:'1530378233579704370'};await props.onSaveConfig(config);await props.onTestConfig(config);
 assert.equal(calls[0][2].leave_channel_id,'1530378233579704370');assert.equal(calls[0][2].leave_embed_data.title,'Bye');assert.equal(calls[0][2].leave_image_url,'https://example.org/bg.png');assert.equal(calls[0][2].leave_auto_delete_duration,60);assert.equal(JSON.stringify(calls[0][2]),JSON.stringify(calls[1][2]));assert.equal(Object.hasOwn(calls[0][2],'leave_enabled'),false);assert.equal(Object.hasOwn(calls[0][2],'welcome_image_enabled'),false);
});
