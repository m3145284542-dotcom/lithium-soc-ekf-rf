import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {Presentation, PresentationFile} from '@oai/artifact-tool';

const root=process.cwd();
const skill='C:/Users/m/.codex/plugins/cache/openai-primary-runtime/presentations/26.1025.11240/skills/presentations';
const build=path.join(root,'work/presentation-build');
const out=path.join(root,'presentation');
const p=Presentation.create({slideSize:{width:1280,height:720}});
const font='Microsoft YaHei';
const ink='#142C42', accent='#066D80', gray='#526574';
const summary=(await fs.readFile(path.join(root,'outputs/experiments/summary.csv'),'utf8')).trim().split(/\r?\n/);
const headers=summary.shift().split(',');
const rows=summary.map(line=>Object.fromEntries(line.split(',').map((v,i)=>[headers[i],v])));
const val=(s,m,k='rmse_pp')=>Number(rows.find(r=>r.scenario===s&&r.method===m)[k]);
const f=v=>v.toFixed(3);
const reduction=s=>((1-val(s,'EKF_RF')/val(s,'EKF'))*100).toFixed(2)+'%';
function txt(s,t,x,y,w,h,size=26,color=ink,bold=false){
 const sh=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 sh.text=t; sh.text.style={typeface:font,fontSize:size,color,bold};return sh;
}
function slide(title,n){const s=p.slides.add();s.background.fill='#FFFFFF';txt(s,title,64,38,1152,82,42,ink,true);txt(s,String(n).padStart(2,'0'),1170,670,50,28,18,gray);return s;}
async function image(s,rel,x,y,w,h){const b=await fs.readFile(path.join(root,rel));s.images.add({blob:b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength),contentType:'image/png',alt:rel,fit:'contain',position:{left:x,top:y,width:w,height:h}});}
function table(s,values,x,y,w,h,widths){
 const tb=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,values,columnWidths:widths});
 tb.borders.assign({fill:'#D8E2E8',width:1,style:'solid'});
 for(let r=0;r<values.length;r++)for(let c=0;c<values[r].length;c++){
  const cell=tb.getCell(r,c);cell.fill=r===0?'#E7F1F3':'#FFFFFF';cell.text.style={typeface:font,fontSize:24,color:ink,bold:r===0};
 }
 return tb;
}
const notes=[];
function note(s,title,seconds,text,sources){notes.push({title,seconds,text,sources});s.speakerNotes.text=`建议用时：${seconds}秒\n\n${text}\n\n来源：${sources.join('；')}`;}

let s=slide('锂电池 SOC 融合估计',1);
txt(s,'扩展卡尔曼滤波与随机森林误差补偿',64,168,1120,80,38,accent,true);
txt(s,'研究问题：动态负载下，如何估计电池剩余电量？',64,296,1120,54,30);
txt(s,'输入：时间、电压、电流、表面温度\n输出：每个采样时刻的 SOC',64,384,1100,105,28);
txt(s,'电气大数据与人工智能 · 课程测试项目\n2026年10月29日',64,566,1100,72,23,gray);
note(s,'问题、目标与应用',30,'我们的项目研究动态负载下的电池剩余电量估计。电压会随着负载和极化变化，不能直接把某个瞬时电压等同于剩余电量。我们先用一阶RC模型和扩展卡尔曼滤波得到SOC，再让随机森林学习剩余误差。输入包括时间、电压、电流和表面温度，最终比较单独EKF与融合方法在留出记录上的表现。',['项目大纲与执行计划.md','README.md']);

s=slide('公开数据与参考 SOC',2);
txt(s,'LG HG2 单节锂电池，25℃环境',64,142,1100,48,30,accent,true);
table(s,[['用途','记录'],['训练','Mixed1–4，共4条'],['验证选方案','Mixed5–6，共2条'],['最终测试','Mixed7–8，共2条']],64,218,640,250,[230,410]);
txt(s,'参考 SOC = 1 − 净放电量 / 2.72639Ah',64,512,1150,52,30);
txt(s,'满电初值近似 + 仪器累计容量\n参考值存在假设误差\n并非独立实测真值',754,233,460,160,26);
txt(s,'按完整记录划分\n相邻采样点不随机拆分',754,424,450,100,27);
txt(s,'Kollmeyer、Naguib、Skells，LG 18650HG2 Li-ion Battery Data，v2\nDOI:10.17632/b5mj79w5w9.2，CC BY 4.0',64,594,1135,66,18,gray);
note(s,'数据与参考SOC',45,'数据来自公开的LG HG2电池实测数据集，环境温度为25摄氏度。29个原始CSV提供容量、低倍率、HPPC脉冲、动态工况及前序充电信息。动态记录一共8条，前4条用于训练，接着2条用于验证选方案，最后2条只作最终测试。参考SOC由满电初始近似和仪器累计容量计算，主容量固定为2.72639安时。前序充电和静置记录支持初始满电假设，但这个SOC仍然是计算基准，有初值和容量误差。我们不把每条记录末端强行归零，也不随机打散相邻采样点。',['data/reference/数据准备报告.md','data/reference/reference_policy.json','data/dataset_manifest.json']);

s=slide('一阶 RC 模型与 EKF',3);
txt(s,'状态：SOC 与极化电压 Up',64,149,1100,48,30,accent,true);
txt(s,'SOC预测\nSOCₖ = SOCₖ₋₁ − I均值Δt / (3600Q)',64,239,1140,95,30);
txt(s,'端电压模型\nVₖ = OCV(SOCₖ) − IₖR₀ − Upₖ',64,378,1140,95,30);
txt(s,'电流积分预测电量，用端电压残差校正状态\n相邻电流均值用于积分，按实际采样间隔更新',64,520,1120,95,27);
txt(s,'R₀ = 17.907mΩ    R₁ = 7.123mΩ    τ = 8.771s\n参数来自42个有效HPPC放电脉冲的中位数，OCV由低倍率带载电压近似',64,627,1100,57,20,gray);
note(s,'电池模型与EKF',50,'一阶RC模型用SOC和极化电压作为状态。SOC预测遵循安时积分，放电电流为正，时间间隔使用原始采样的真实间隔。极化电压按RC时间常数衰减，并受电流驱动。端电压由开路电压扣除欧姆压降和极化压降得到。EKF先用模型预测，再比较实测电压与预测电压，通过残差更新状态。低倍率放电用于近似OCV，HPPC的42个有效放电脉冲用于辨识电阻和时间常数。这里采用固定参数，尚未描述温度、SOC和充放电方向对参数的影响，所以模型仍可能留下系统误差。',['src/ekf.py','src/battery.py','outputs/model/建模报告.md','outputs/model/battery_parameters.json']);

s=slide('随机森林学习 EKF 的剩余误差',4);
txt(s,'训练标签：参考 SOC − EKF SOC',64,148,1130,52,32,accent,true);
txt(s,'7个输入特征',64,243,440,45,30,ink,true);
txt(s,'EKF SOC、端电压、电流、表面温度\n校正前电压残差\n过去5秒电流均值、窗口电压变化量',64,309,1120,142,28);
txt(s,'融合 SOC = clip(EKF SOC + 预测修正量, 0, 1)',64,485,1150,65,31,accent,true);
txt(s,'只用当前与历史采样，不输入参考SOC或累计容量\n修正量只作用于最终输出，不回灌EKF内部状态',64,583,1140,77,25,gray);
note(s,'随机森林补偿',75,'随机森林不直接替代整个电池模型，而是预测EKF还剩多少误差。训练标签等于参考SOC减EKF输出。输入一共7个特征，包括EKF的SOC、电压、电流、表面温度、校正前电压残差，以及过去5秒电流的样本均值和电压变化量。窗口只读取当前及过去的数据，跨数据间断时重新开始。参考SOC和累计容量只用于标签和评价，不作为推理特征。森林有120棵树，最大深度12，叶节点最少50个样本。我们只在4条训练记录上拟合，比较两组候选在2条验证记录上的平均RMSE，选好后固定模型，没有把验证集追加回训练。推理时把预测修正量加到EKF的SOC上，再限制在零到一之间。补偿不回灌EKF，因此改善最终输出并不等同于改变滤波器内部收敛过程。',['outputs/correction/training_config.json','src/correction.py','outputs/correction/补偿建模报告.md']);

s=slide('正常测试平均 RMSE 降低 '+reduction('normal'),5);
await image(s,'outputs/figures/experiments/normal_552_Mixed7_soc.png',36,156,748,365);
table(s,[['记录','EKF','融合'],['Mixed7','2.231','1.066'],['Mixed8','2.001','0.886']],800,214,416,205,[150,133,133]);
txt(s,'RMSE，单位：SOC百分点',800,438,410,44,21,gray);
txt(s,`${f(val('normal','EKF'))}  →  ${f(val('normal','EKF_RF'))}`,64,555,700,66,44,accent,true);
txt(s,'先按记录计算RMSE，再对两条记录等权平均\n平均MAE：1.770降至0.801个SOC百分点',64,627,1100,57,21,gray);
note(s,'正常工况结果',80,`这页给出完全留出的Mixed7和Mixed8的正常测试结果。左图展示Mixed7的参考SOC、单独EKF和融合输出，右表给出两条记录各自的RMSE。Mixed7从2.231降到1.066个SOC百分点，Mixed8从2.001降到0.886。先分别计算每条记录的RMSE，再作等权平均，得到${f(val('normal','EKF'))}降到${f(val('normal','EKF_RF'))}，相对降低${reduction('normal')}。它不是把所有采样合并计算的RMSE。平均MAE也从1.770降到0.801。两种方法使用相同输入，全部有效采样从首个更新后输出开始计分，没有截去初始阶段。平均改善也有局部例外，正常组Mixed7的融合最大绝对误差仍约3.597个百分点。这里的误差都是相对于计算参考值，不能写成独立测量意义上的绝对精度。`,['outputs/experiments/metrics.csv','outputs/experiments/summary.csv','outputs/experiments/实验报告.md','outputs/figures/experiments/normal_552_Mixed7_soc.png']);

s=slide('初始偏差与噪声下的误差',6);
table(s,[['实验','EKF平均RMSE','融合平均RMSE','相对降低'],...['normal','initial_bias','measurement_noise'].map((a,i)=>[['正常','初始低估10百分点','测量噪声'][i],f(val(a,'EKF')),f(val(a,'EKF_RF')),reduction(a)])],64,146,1152,208,[360,280,280,232]);
await image(s,'outputs/figures/experiments/initial_bias_552_Mixed7_error.png',44,390,750,258);
txt(s,'初始偏差组首点仍约4百分点误差\n融合只修正输出',818,405,392,106,25);
txt(s,'噪声标准差\n电压0.01V，电流0.05A\n单次固定随机实现',818,525,392,114,23,gray);
txt(s,'单位：SOC百分点。初始偏差与加噪分别施加，两种方法共用同一组输入。',64,668,1090,28,18,gray);
note(s,'干扰实验与误差分析',50,'我们还做了两组独立干扰实验，一组把初始SOC由一改为零点九，另一组只给电压和电流加入标准差分别为0.01伏和0.05安的高斯噪声，二者不叠加。模型保持固定，两种方法共用相同扰动输入。两组平均RMSE仍改善，但初始偏差组在首个电压校正后的融合输出仍有约4个百分点误差，所以不能只报平均值，也不能宣称提高了EKF内部收敛速度。噪声只做了一次固定种子实现，目前无法据此判断多次随机重复下的稳定性。',['outputs/experiments/experiment_config.json','outputs/experiments/实验报告.md','outputs/experiments/summary.csv']);

s=slide('结论与工作记录',7);
txt(s,'当前测试中，随机森林补偿降低了平均SOC误差',64,150,1150,88,35,accent,true);
txt(s,'结论范围',64,278,1120,44,30,ink,true);
txt(s,'同一电芯、25℃环境、两条留出混合工况\n参考SOC依赖满电与容量假设，局部仍有较大误差',64,344,1130,98,28);
txt(s,'工作记录',64,488,1100,44,30,ink,true);
txt(s,'数据与参考SOC、RC/EKF、森林补偿、实验与汇报\n个人贡献以实际核实记录为准，见随附成员填写表',64,550,1130,100,27);
note(s,'结论与分工',30,'本项目完成了从公开数据、参考SOC、电池建模到误差补偿和留出测试的完整流程。当前实验支持随机森林降低平均误差，但证据范围限于同一电芯和两条留出记录。后续可以增加电芯和温度范围，并开展多次噪声重复实验。工作记录覆盖数据、建模、补偿、实验与汇报，实际成员贡献请以随附表中的真实核实记录为准。',['README.md','presentation/贡献记录与个人反思.md','outputs/experiments/实验报告.md']);

await fs.mkdir(out,{recursive:true});
await fs.writeFile(path.join(out,'6分钟讲稿与答辩.md'),'# 6分钟讲稿与答辩\n\n7页，建议合计360秒。建议时长是演练目标，尚未进行真人计时。请先补充实际组员信息，并根据本人讲述速度删改。PPT备注中也包含各页讲稿与来源。\n\n'+notes.map((n,i)=>`## 第${i+1}页：${n.title}（${n.seconds}秒）\n\n${n.text}\n\n来源：${n.sources.map(a=>'`'+a+'`').join('、')}\n`).join('\n')+`\n## 常见答辩问题\n\n**为什么不能直接用电压看SOC？**\n动态负载引起欧姆压降和极化，瞬时端电压同时反映电量与负载影响，需要模型和测量共同估计。\n\n**参考SOC是真值吗？**\n它由起点满电近似、仪器累计容量和固定容量计算。前序充电及静置提供依据，但初值、容量及计数器误差仍会影响参考，不能称独立实测真值。\n\n**为什么用随机森林？**\n用于学习测量信息和EKF残差之间的非线性补偿关系，课程项目易于实现。这里只比较两组森林候选，没有证据说明它优于所有其他学习算法。\n\n**如何避免训练测试混用？**\n按完整工况4/2/2划分，4条拟合、2条选方案、2条固定后测试。参考SOC、累计容量和未来采样不作为推理特征，验证记录未追加回训练。\n\n**53.89%如何算？**\n先计算两条记录各自RMSE，再对两条等权平均，用(2.1162460355−0.9759046730)/2.1162460355计算降低比例。分子与分母均使用未四舍五入的值。\n\n**初始SOC设为0.9，为什么首点误差不是−10？**\n0.9是电压更新前的初始状态，保存和评分的首点已经过电压校正。融合随后还进行输出补偿。\n\n**加噪结果略好，是否说明噪声有益？**\n不能。本项目只做一次固定噪声实现，非线性模型和特征变化可能让特定误差指标略降，仍需多次重复才可判断。\n\n**融合能加快EKF收敛吗？**\n本实现不把修正量反馈给EKF状态，只说明最终输出误差变化，不能据此断言提高滤波器内部收敛速度。\n\n**可以用于真实BMS吗？**\n当前是课程测试版本，只验证同一电芯25℃环境下的两条记录，尚缺跨电芯、温度、老化及实时部署实验。\n\n**AI做了哪些工作？**\n项目使用Codex辅助代码、实验与材料整理。按成员实际核查、修改和复现情况说明个人工作，详见贡献记录，不能把自动生成内容当作所有成员独立完成。\n`);

const candidate=path.join(build,'candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(candidate);
for(const [i,s] of p.slides.items.entries()){
 await fs.writeFile(path.join(build,`slide-${i+1}.png`),new Uint8Array(await (await p.export({slide:s,format:'png',scale:1})).arrayBuffer()));
}
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const result=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:path.join(out,'SOC融合估计_6分钟汇报.pptx'),pythonExecutable:'C:/Users/m/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit',...[2,5,6].flatMap(n=>['--require-native-table-slide',String(n)])],explicitTotalSlideCount:7,requiredNativeTableOwnerSlides:[2,5,6],fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,receiptPath:path.join(build,'validation.json')});
console.log(JSON.stringify(result));
