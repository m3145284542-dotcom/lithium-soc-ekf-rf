// 优化版 6 分钟汇报：数值均读取项目正式输出，讲稿取自 6分钟讲稿与答辩.md
const fs = require('fs');
const path = require('path');
const pptxgen = require('pptxgenjs');

const ROOT = 'D:/document/电气大数据与人工智能';
const OUT = path.join(ROOT, 'presentation/SOC融合估计_6分钟汇报_优化版.pptx');
const FONT = 'Microsoft YaHei';
const NAVY = '0F2A3A', TEAL = '0E7C86', EKF = '8E7CC3', AMBER = 'E09B2D',
  INK = '142C42', GRAY = '5B6B76', CARD = 'F1F5F7', LINE = 'D5E0E5', LIGHT = 'A9DDE0';

// ---------- 数据 ----------
const csv = f => {
  const [h, ...r] = fs.readFileSync(path.join(ROOT, f), 'utf8').trim().split(/\r?\n/);
  const k = h.split(',');
  return r.map(l => Object.fromEntries(l.split(',').map((v, i) => [k[i], v])));
};
const summary = csv('outputs/experiments/summary.csv');
const metrics = csv('outputs/experiments/metrics.csv');
const importance = csv('outputs/correction/feature_importance.csv');
const baseline = csv('outputs/baseline/summary.csv');
const bv = (sc, m, k = 'rmse_pp') => Number(baseline.find(r => r.scenario === sc && r.method === m)[k]);
const OFF = 'B8C2C8';
const sv = (s, m, k = 'rmse_pp') => Number(summary.find(r => r.scenario === s && r.method === m)[k]);
const mv = (s, file, m) => Number(metrics.find(r => r.scenario === s && r.file === file && r.method === m).rmse_pp);
const f3 = v => v.toFixed(3);
const red = s => ((1 - sv(s, 'EKF_RF') / sv(s, 'EKF')) * 100).toFixed(2) + '%';

// 讲稿：按“## 第N页”拆分，正文为“来源”之前的段落
const md = fs.readFileSync(path.join(ROOT, 'work/presentation-build/讲稿_7页旧版.md'), 'utf8').replace(/\r\n/g, '\n');
const notes = [];
for (const m of md.matchAll(/## 第(\d)页：(.+?)（(\d+)秒）\n\n([\s\S]+?)\n\n来源：(.+)/g))
  notes[Number(m[1])] = `建议用时：${m[3]}秒\n\n${m[4].trim()}\n\n来源：${m[5].replace(/`/g, '')}`;

// ---------- 版式 ----------
const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE';
pres.title = '锂电池 SOC 融合估计';
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };

pres.defineSlideMaster({
  title: 'CONTENT',
  background: { color: 'FFFFFF' },
  objects: [{ placeholder: { options: { name: 'title', type: 'title', x: 0.6, y: 0.35, w: 12.1, h: 0.8,
    fontFace: FONT, fontSize: 32, bold: true, color: INK, valign: 'middle', align: 'left', margin: 0 }, text: '' } }],
  slideNumber: { x: 12.3, y: 6.95, w: 0.5, h: 0.3, fontFace: FONT, fontSize: 11, color: GRAY, align: 'right' },
});
pres.defineSlideMaster({ title: 'DARK', background: { color: NAVY } });

const T = (s, text, o) => s.addText(text, { isTextBox: true, fontFace: FONT, color: INK, margin: 0, valign: 'top', ...o });
const card = (s, x, y, w, h, fill = CARD) =>
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: fill } });
const arrow = (s, x, y, w = 0.35, color = GRAY) =>
  s.addShape(pres.shapes.RIGHT_ARROW, { x, y, w, h: 0.28, fill: { color }, line: { color } });
const img = (s, rel, x, y, w, h) => s.addImage({ path: path.join(ROOT, rel), x, y, w, h, altText: rel });
const content = (title, n) => { const s = pres.addSlide({ masterName: 'CONTENT' }); s.addText(title, { placeholder: 'title' }); s.addNotes(notes[n]); return s; };
const chartBase = {
  barDir: 'col', barGrouping: 'clustered', chartColors: [EKF, TEAL],
  catAxisLabelFontFace: FONT, valAxisLabelFontFace: FONT, legendFontFace: FONT, dataLabelFontFace: FONT,
  catAxisLabelColor: GRAY, valAxisLabelColor: GRAY, catAxisLabelFontSize: 12, valAxisLabelFontSize: 11,
  valGridLine: { color: 'E3EAEE', size: 0.75 }, catGridLine: { style: 'none' },
  showValue: true, dataLabelPosition: 'outEnd', dataLabelFontSize: 12, dataLabelColor: INK, dataLabelFormatCode: '0.000',
  showLegend: true, legendPos: 't', legendFontSize: 12, legendColor: INK,
  showTitle: true, titleFontFace: FONT, titleFontSize: 14, titleColor: INK,
  valAxisMinVal: 0, barGapWidthPct: 60,
};

// ---------- 1 封面 ----------
let s = pres.addSlide({ masterName: 'DARK' });
s.addNotes(notes[1]);
T(s, '电气大数据与人工智能 · 课程项目', { x: 0.8, y: 0.9, w: 8, h: 0.4, fontSize: 16, color: LIGHT });
T(s, '锂电池 SOC 融合估计', { x: 0.8, y: 1.5, w: 11, h: 1.0, fontSize: 48, bold: true, color: 'FFFFFF' });
T(s, '扩展卡尔曼滤波 + 随机森林误差补偿', { x: 0.8, y: 2.6, w: 11, h: 0.6, fontSize: 26, color: LIGHT });
T(s, '研究问题：动态负载下，仅凭电压、电流、温度，如何可靠估计剩余电量？', { x: 0.8, y: 3.45, w: 11.5, h: 0.5, fontSize: 18, color: 'D9E6EA' });
['公开实测数据', '一阶RC + EKF', '随机森林补偿'].forEach((t, i) => {
  const x = 0.8 + i * 2.55;
  card(s, x, 4.45, 2.1, 0.75, '1C4459');
  T(s, t, { x, y: 4.45, w: 2.1, h: 0.75, fontSize: 16, bold: true, color: 'FFFFFF', align: 'center', valign: 'middle' });
  if (i < 2) arrow(s, x + 2.15, 4.69, 0.35, LIGHT);
});
T(s, '−' + red('normal'), { x: 8.9, y: 4.15, w: 3.8, h: 1.0, fontSize: 54, bold: true, color: AMBER, align: 'right' });
T(s, '留出测试平均 RMSE 降低', { x: 8.9, y: 5.15, w: 3.8, h: 0.4, fontSize: 15, color: 'D9E6EA', align: 'right' });
T(s, '小组成员：（待填写）        2026年10月29日', { x: 0.8, y: 6.55, w: 10, h: 0.4, fontSize: 14, color: '8FA6B2' });

// ---------- 2 数据 ----------
s = content('公开数据与参考 SOC', 2);
T(s, 'LG HG2 单节锂电池 · 25℃ · 8条动态工况按完整记录划分', { x: 0.6, y: 1.3, w: 7.2, h: 0.4, fontSize: 16, bold: true, color: TEAL });
const split = [['训练', 4, TEAL], ['验证选方案', 2, AMBER], ['最终测试', 2, NAVY]];
let k = 1, bx = 0.6;
split.forEach(([label, n, c]) => {
  for (let i = 0; i < n; i++, k++, bx += 0.86) {
    card(s, bx, 1.95, 0.78, 0.62, c);
    T(s, 'Mixed' + k, { x: bx, y: 1.95, w: 0.78, h: 0.62, fontSize: 11, bold: true, color: 'FFFFFF', align: 'center', valign: 'middle' });
  }
  T(s, `${label}（${n}条）`, { x: bx - n * 0.86, y: 2.65, w: n * 0.86 - 0.08, h: 0.35, fontSize: 13, color: c, bold: true, align: 'center' });
});
card(s, 0.6, 3.3, 6.8, 1.0);
T(s, [{ text: '参考 SOC = 1 − 净放电量 / 2.72639 Ah', options: { fontSize: 22, bold: true, color: INK, breakLine: true } },
  { text: '起点满电近似 + 仪器累计容量；主容量取 551_Cap_1C', options: { fontSize: 13, color: GRAY } }],
  { x: 0.85, y: 3.42, w: 6.4, h: 0.8 });
const pts = [['满电依据', '前序充电末端约4.2V / 48.5mA，并静置约61分钟'],
  ['防止泄漏', '训练/验证/测试按整条记录划分，测试集不参与调参'],
  ['参考边界', '参考值是计算基准，含初值与容量误差，非独立实测真值']];
pts.forEach(([h, b], i) => {
  const y = 4.55 + i * 0.6;
  s.addShape(pres.shapes.OVAL, { x: 0.62, y: y + 0.08, w: 0.2, h: 0.2, fill: { color: TEAL }, line: { color: TEAL } });
  T(s, [{ text: h + '  ', options: { bold: true, color: INK } }, { text: b, options: { color: GRAY } }],
    { x: 0.95, y, w: 6.5, h: 0.45, fontSize: 14, valign: 'middle' });
});
T(s, 'Kollmeyer, Naguib, Skells. LG 18650HG2 Li-ion Battery Data, v2. DOI:10.17632/b5mj79w5w9.2, CC BY 4.0',
  { x: 0.6, y: 6.6, w: 7.2, h: 0.5, fontSize: 10, color: GRAY });
img(s, 'outputs/figures/Mixed1_inputs_reference.png', 8.1, 1.3, 4.58, 5.6);

// ---------- 3 模型 ----------
s = content('一阶 RC 模型与 EKF', 3);
const eqs = [['状态预测（安时积分 + 极化衰减）',
  'SOCₖ = SOCₖ₋₁ − Ī·Δt / (3600·Q)\nUpₖ = a·Upₖ₋₁ + R₁(1 − a)·Ī，  a = e^(−Δt/τ)'],
  ['观测方程（端电压）', 'Vₖ = OCV(SOCₖ) − Iₖ·R₀ − Upₖ']];
let ey = 1.35;
eqs.forEach(([h, e], i) => {
  const hh = i ? 1.25 : 1.7;
  card(s, 0.6, ey, 6.1, hh);
  T(s, h, { x: 0.85, y: ey + 0.15, w: 5.7, h: 0.35, fontSize: 14, bold: true, color: TEAL });
  T(s, e, { x: 0.85, y: ey + 0.55, w: 5.7, h: hh - 0.65, fontSize: 19, color: INK, fontFace: 'Cambria Math' });
  ey += hh + 0.3;
});
T(s, 'EKF 每个采样的循环', { x: 0.6, y: 4.75, w: 6, h: 0.35, fontSize: 14, bold: true, color: INK });
['模型预测', '电压残差', '卡尔曼增益修正'].forEach((t, i) => {
  const x = 0.6 + i * 2.1;
  card(s, x, 5.2, 1.75, 0.7, i === 1 ? TEAL : NAVY);
  T(s, t, { x, y: 5.2, w: 1.75, h: 0.7, fontSize: 14, bold: true, color: 'FFFFFF', align: 'center', valign: 'middle' });
  if (i < 2) arrow(s, x + 1.78, 5.41, 0.28);
});
T(s, '按真实采样间隔递推，不跨数据间断；初始 SOC=1、Up=0', { x: 0.6, y: 6.1, w: 6.2, h: 0.4, fontSize: 13, color: GRAY });
img(s, 'outputs/figures/model/ocv_curve.png', 7.1, 1.35, 5.6, 2.92);
T(s, '近似 OCV：549_C20 低倍率放电带载电压', { x: 7.1, y: 4.3, w: 5.6, h: 0.3, fontSize: 11, color: GRAY });
[['R₀', '17.907', 'mΩ'], ['R₁', '7.123', 'mΩ'], ['τ', '8.771', 's']].forEach(([n, v, u], i) => {
  const x = 7.1 + i * 1.95;
  card(s, x, 4.8, 1.75, 1.15);
  T(s, n, { x: x + 0.15, y: 4.88, w: 1.5, h: 0.3, fontSize: 13, color: GRAY });
  T(s, [{ text: v, options: { fontSize: 24, bold: true, color: TEAL } }, { text: ' ' + u, options: { fontSize: 13, color: GRAY } }],
    { x: x + 0.15, y: 5.2, w: 1.55, h: 0.6 });
});
T(s, '42个有效HPPC放电脉冲参数中位数；未建模温度与方向影响',
  { x: 7.1, y: 6.1, w: 5.6, h: 0.5, fontSize: 12, color: GRAY });

// ---------- 4 随机森林 ----------
s = content('随机森林学习 EKF 的剩余误差', 4);
const flow = [['测量', '电压·电流·温度', NAVY], ['EKF', 'SOC + 电压残差', EKF], ['7个因果特征', '只用当前与历史5秒', NAVY],
  ['随机森林', '预测修正量 ΔSOC', TEAL], ['融合 SOC', 'clip(EKF + ΔSOC, 0, 1)', AMBER]];
flow.forEach(([h, b, c], i) => {
  const x = 0.6 + i * 2.48;
  card(s, x, 1.35, 2.1, 1.15, c);
  T(s, [{ text: h, options: { fontSize: 16, bold: true, breakLine: true } }, { text: b, options: { fontSize: 12 } }],
    { x: x + 0.05, y: 1.35, w: 2.0, h: 1.15, color: 'FFFFFF', align: 'center', valign: 'middle' });
  if (i < 4) arrow(s, x + 2.12, 1.79, 0.32);
});
const fname = { soc_ekf: 'EKF SOC', temperature_degC: '表面温度', voltage_residual_v: '电压残差', current_mean_5s_a: '5秒电流均值',
  voltage_v: '端电压', voltage_change_5s_v: '5秒电压变化', current_a: '电流' };
const imp = [...importance].reverse();
s.addChart(pres.charts.BAR, [{ name: '重要性', labels: imp.map(r => fname[r.feature]), values: imp.map(r => Number(r.impurity_importance) * 100) }], {
  ...chartBase, x: 0.6, y: 2.85, w: 6.4, h: 3.75, barDir: 'bar', chartColors: [TEAL], showLegend: false,
  title: '特征重要性（不纯度，%）', dataLabelFormatCode: '0.0', valAxisHidden: true, valGridLine: { style: 'none' },
});
card(s, 7.4, 2.85, 5.3, 3.75);
const rf = [['训练标签', '参考 SOC − EKF SOC'], ['模型', '120棵树，最大深度12，叶节点≥50'],
  ['选型', '4条训练拟合 → 2条验证选方案 → 固定后测试'], ['不使用', '参考SOC、累计容量、未来采样'], ['不回灌', '修正量只作用于输出，不改EKF内部状态']];
rf.forEach(([h, b], i) => T(s, [{ text: h, options: { bold: true, color: TEAL, breakLine: true } }, { text: b, options: { color: INK } }],
  { x: 7.65, y: 3.0 + i * 0.68, w: 4.9, h: 0.65, fontSize: 14 }));
T(s, '温度与 EKF SOC 占主导：温度可能部分反映放电进程，跨温度泛化需另行验证',
  { x: 0.6, y: 6.65, w: 12, h: 0.35, fontSize: 12, color: GRAY });

// ---------- 5 正常工况结果 ----------
s = content(`正常测试：平均 RMSE 降低 ${red('normal')}`, 5);
img(s, 'outputs/figures/experiments/normal_552_Mixed7_soc.png', 0.6, 1.3, 6.9, 3.6);
s.addChart(pres.charts.BAR, [
  { name: 'EKF', labels: ['Mixed7', 'Mixed8'], values: [mv('normal', '552_Mixed7.csv', 'EKF'), mv('normal', '552_Mixed8.csv', 'EKF')] },
  { name: 'EKF + RF', labels: ['Mixed7', 'Mixed8'], values: [mv('normal', '552_Mixed7.csv', 'EKF_RF'), mv('normal', '552_Mixed8.csv', 'EKF_RF')] },
], { ...chartBase, x: 7.8, y: 1.3, w: 4.9, h: 3.6, title: '逐记录 RMSE（SOC 百分点）', valAxisMaxVal: 2.6 });
const stats = [[`${f3(sv('normal', 'EKF'))} → ${f3(sv('normal', 'EKF_RF'))}`, '平均 RMSE（pp），两条记录等权平均', TEAL],
  [`${f3(sv('normal', 'EKF', 'mae_pp'))} → ${f3(sv('normal', 'EKF_RF', 'mae_pp'))}`, '平均 MAE（pp）', TEAL],
  [f3(sv('normal', 'EKF_RF', 'worst_max_abs_error_pp')), '融合最大绝对误差（pp）：局部仍有误差', AMBER]];
stats.forEach(([v, l, c], i) => {
  const x = 0.6 + i * 4.1;
  card(s, x, 5.25, 3.85, 1.4);
  T(s, v, { x: x + 0.25, y: 5.38, w: 3.4, h: 0.7, fontSize: 30, bold: true, color: c });
  T(s, l, { x: x + 0.25, y: 6.1, w: 3.5, h: 0.4, fontSize: 13, color: GRAY });
});

// ---------- 6 干扰实验 ----------
s = content('干扰实验与简单基线对比', 6);
const sc = [['normal', '正常'], ['initial_bias', '初始低估10pp'], ['measurement_noise', '测量噪声']];
s.addChart(pres.charts.BAR, [
  { name: 'EKF', labels: sc.map(x => x[1]), values: sc.map(x => sv(x[0], 'EKF')) },
  { name: '常值偏置校正', labels: sc.map(x => x[1]), values: sc.map(x => bv(x[0], 'EKF_offset')) },
  { name: 'EKF + RF', labels: sc.map(x => x[1]), values: sc.map(x => sv(x[0], 'EKF_RF')) },
], { ...chartBase, chartColors: [EKF, OFF, TEAL], dataLabelFontSize: 10, barGapWidthPct: 40,
  x: 0.6, y: 1.3, w: 6.6, h: 3.65, title: '等记录平均 RMSE（SOC 百分点）', valAxisMaxVal: 2.6 });
img(s, 'outputs/figures/experiments/initial_bias_552_Mixed7_error.png', 7.4, 1.3, 5.3, 2.76);
T(s, 'Mixed7 初始 SOC=0.9 的误差曲线：融合输出有局部抖动。模型固定不重训，各方法共用同一扰动输入，两种扰动分别施加', { x: 7.4, y: 4.15, w: 5.3, h: 0.7, fontSize: 11, color: GRAY });
const cav = [['初始偏差', `降低 ${red('initial_bias')}；首个校正后融合仍约4pp误差，不能宣称加快EKF收敛`],
  ['测量噪声', `降低 ${red('measurement_noise')}；电压0.01V、电流0.05A，仅一次固定种子实现`],
  ['简单基线', `训练集平均偏置 +${JSON.parse(fs.readFileSync(path.join(ROOT, 'outputs/baseline/baseline_config.json'), 'utf8')).offset_pp.toFixed(2)}pp 已降 ${bv('normal','EKF_offset','rmse_reduction_vs_ekf_pct').toFixed(1)}%；RF 再降约 ${(bv('normal','EKF_offset')-sv('normal','EKF_RF')).toFixed(2)}pp，但最大误差更大`]];
cav.forEach(([h, b], i) => {
  const x = 0.6 + i * 4.1;
  card(s, x, 5.2, 3.85, 1.5);
  T(s, h, { x: x + 0.25, y: 5.32, w: 3.4, h: 0.35, fontSize: 15, bold: true, color: TEAL });
  T(s, b, { x: x + 0.25, y: 5.72, w: 3.4, h: 0.9, fontSize: 13, color: INK });
});

// ---------- 7 结论 ----------
s = pres.addSlide({ masterName: 'DARK' });
s.addNotes(notes[7]);
T(s, '结论与展望', { x: 0.8, y: 0.6, w: 11, h: 0.8, fontSize: 36, bold: true, color: 'FFFFFF' });
T(s, '在两条留出记录上，随机森林补偿将 EKF 平均 SOC 误差降低约一半', { x: 0.8, y: 1.5, w: 11.8, h: 0.5, fontSize: 20, color: AMBER, bold: true });
const cols = [['结论', [`三组实验平均RMSE均降低 ${red('initial_bias')}～${red('measurement_noise')}`, `其中约${Math.round((sv('normal','EKF')-bv('normal','EKF_offset'))/(sv('normal','EKF')-sv('normal','EKF_RF'))*100)}%来自去除EKF固定偏差`]],
  ['边界', ['同一电芯、25℃、两条留出工况', '参考SOC为计算基准；局部误差仍可达约3.6～4.4pp']],
  ['下一步', ['扩展电芯、温度与老化数据', '多次噪声重复；抑制补偿输出的局部抖动']]];
cols.forEach(([h, items], i) => {
  const x = 0.8 + i * 4.0;
  card(s, x, 2.4, 3.7, 2.7, '1C4459');
  T(s, h, { x: x + 0.3, y: 2.6, w: 3.1, h: 0.45, fontSize: 20, bold: true, color: LIGHT });
  T(s, items.map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < items.length - 1, paraSpaceAfter: 10 } })),
    { x: x + 0.3, y: 3.2, w: 3.15, h: 1.8, fontSize: 15, color: 'FFFFFF' });
});
T(s, '分工：数据与参考SOC · RC/EKF · 森林补偿 · 实验与汇报 —— 成员贡献见随附贡献记录表', { x: 0.8, y: 5.6, w: 11.8, h: 0.4, fontSize: 14, color: '8FA6B2' });

if (notes.filter(Boolean).length !== 7) throw new Error('讲稿解析失败：应有7页备注');
pres.writeFile({ fileName: OUT }).then(f => console.log('wrote', f));
