// 课堂展示可编辑版：文字放在形状内部、数字与单位同字体同行、图表为原生可编辑图表
const fs = require('fs');
const path = require('path');
const pptxgen = require('pptxgenjs');

const ROOT = 'D:/document/电气大数据与人工智能';
const OUT = path.join(ROOT, 'presentation/SOC融合估计_课堂展示_可编辑版.pptx');
const FONT = 'Microsoft YaHei';
const C = {
  bg: '0B1622', panel: '12263A', panel2: '0F3340', line: '24405A', cyan: '22D3EE', green: 'A3E635',
  violet: 'A78BFA', gray: '7C8DA3', amber: 'FBBF24', text: 'E6EDF5', sub: '93A4B8', white: 'FFFFFF', dark: '0B1622',
};
const px = v => v / 96;            // 设计稿 1280×720 px → 英寸
const pt = v => Math.round(v * 0.75 * 2) / 2;   // px 字号 → pt

// ---------- 数据 ----------
const csv = f => {
  const [h, ...r] = fs.readFileSync(path.join(ROOT, f), 'utf8').trim().split(/\r?\n/);
  const k = h.split(',');
  return r.map(l => Object.fromEntries(l.split(',').map((v, i) => [k[i], v])));
};
const summary = csv('outputs/experiments/summary.csv');
const metrics = csv('outputs/experiments/metrics.csv');
const baseline = csv('outputs/baseline/summary.csv');
const importance = csv('outputs/correction/feature_importance.csv');
const sv = (s, m, k = 'rmse_pp') => Number(summary.find(r => r.scenario === s && r.method === m)[k]);
const mv = (file, m) => Number(metrics.find(r => r.scenario === 'normal' && r.file === file && r.method === m).rmse_pp);
const bv = s => Number(baseline.find(r => r.scenario === s && r.method === 'EKF_offset').rmse_pp);

const md = fs.readFileSync(path.join(ROOT, 'presentation/6分钟讲稿与答辩.md'), 'utf8').replace(/\r\n/g, '\n');
const notes = [];
for (const m of md.matchAll(/## 第(\d)页：(.+?)（(\d+)秒）\n\n([\s\S]+?)\n\n来源：/g))
  notes[Number(m[1])] = `建议用时：${m[3]}秒\n\n${m[4].trim()}`;
if (notes.filter(Boolean).length !== 9) throw new Error('讲稿解析失败：应有9页');

// ---------- 版式 ----------
const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE';
pres.title = '锂电池 SOC 融合估计';
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };

const gridLines = (step, op) => {
  const o = [];
  for (let y = step; y < 720; y += step) o.push({ line: { x: 0, y: px(y), w: px(1280), h: 0, line: { color: C.line, width: 0.75, transparency: op } } });
  for (let x = step; x < 1280; x += step) o.push({ line: { x: px(x), y: 0, w: 0, h: px(720), line: { color: C.line, width: 0.75, transparency: op } } });
  return o;
};
pres.defineSlideMaster({ title: 'CONTENT', background: { color: C.bg }, objects: gridLines(160, 65) });
pres.defineSlideMaster({ title: 'ANCHOR', background: { color: C.bg }, objects: gridLines(80, 60) });

// pptxgenjs 的 margin 顺序是 [左, 右, 下, 上]（单位 pt）；这里统一按 [上, 右, 下, 左] 书写
const inset = m => Array.isArray(m) ? [m[3], m[1], m[2], m[0]] : m;
// 带文字的形状：文字始终在框内，可直接编辑
function box(s, x, y, w, h, runs, o = {}) {
  s.addText(runs, {
    x: px(x), y: px(y), w: px(w), h: px(h), shape: o.shape || pres.shapes.ROUNDED_RECTANGLE, rectRadius: o.radius ?? 0.1,
    fill: o.fill ? { color: o.fill } : { type: 'none' }, line: o.line ? { color: o.line, width: o.lineW || 1 } : { type: 'none' },
    fontFace: FONT, color: o.color || C.text, fontSize: pt(o.size || 19), bold: !!o.bold,
    align: o.align || 'left', valign: o.valign || 'top', margin: inset(o.margin ?? [12, 16, 12, 16]),
    paraSpaceAfter: o.gap ?? 0, lineSpacingMultiple: o.leading || 1.15, fit: 'none', isTextBox: !o.fill && !o.line,
  });
}
const r = (text, o = {}) => ({ text, options: { fontFace: FONT, ...o, ...(o.size ? { fontSize: pt(o.size) } : {}) } });
const br = (text, o = {}) => r(text, { ...o, breakLine: true });
function title(s, t, n) {
  s.addText(t, { x: px(56), y: px(40), w: px(840), h: px(64), fontFace: FONT, fontSize: pt(36), bold: true, color: C.white, margin: 0, valign: 'middle', isTextBox: true });
  const labels = ['问题', '数据', '算法', '结论', '意义'];
  s.addText(labels.flatMap((l, i) => [r(l, { color: l === n ? C.cyan : C.sub, bold: l === n }), ...(i < 4 ? [r('　', {})] : [])]),
    { x: px(880), y: px(52), w: px(344), h: px(40), fontFace: FONT, fontSize: pt(18), align: 'right', valign: 'middle', margin: 0, isTextBox: true });
}
function figure(s, rel, x, y, w, h) {
  box(s, x, y, w, h, '', { fill: 'F4F7FA', line: C.cyan, lineW: 1.25, margin: 0 });
  s.addImage({ path: path.join(ROOT, rel), x: px(x + 10), y: px(y + 10), w: px(w - 20), h: px(h - 20), sizing: { type: 'contain', w: px(w - 20), h: px(h - 20) }, altText: rel });
}
const arrow = (s, x, y, w = 34, h = 26) => s.addShape(pres.shapes.RIGHT_ARROW, { x: px(x), y: px(y), w: px(w), h: px(h), fill: { color: C.cyan }, line: { type: 'none' } });
const chartBase = {
  catAxisLabelFontFace: FONT, valAxisLabelFontFace: FONT, dataLabelFontFace: FONT, legendFontFace: FONT,
  catAxisLabelColor: C.text, valAxisLabelColor: C.sub, catAxisLabelFontSize: 12, valAxisLabelFontSize: 11,
  catAxisLineShow: true, valAxisLineShow: false, catAxisLineColor: C.sub,
  valGridLine: { color: C.line, size: 0.75 }, catGridLine: { style: 'none' },
  showValue: true, dataLabelPosition: 'outEnd', dataLabelFontSize: 12, dataLabelColor: C.text, dataLabelFontBold: true,
  showLegend: false, legendColor: C.text, legendFontSize: 12,
  plotArea: { fill: { color: C.panel } }, valAxisMinVal: 0,
};

// ---------- 1 封面 ----------
let s = pres.addSlide({ masterName: 'ANCHOR' });
s.addNotes(notes[1]);
s.addShape(pres.shapes.OVAL, { x: px(730), y: px(270), w: px(600), h: px(400), fill: { color: C.cyan, transparency: 88 }, line: { type: 'none' } });
box(s, 56, 84, 900, 200, [
  br('电气大数据与人工智能 · 课程项目', { size: 16, color: C.cyan }),
  br('锂电池 SOC 融合估计', { size: 60, bold: true, color: C.white }),
  r('扩展卡尔曼滤波 + 随机森林误差补偿', { size: 24, color: 'A9E7F2' }),
], { margin: 0, gap: 6 });
box(s, 56, 306, 900, 40, '研究问题：电池忽快忽慢地用电时，怎样准确知道还剩多少电？', { margin: 0 });
[['公开实测数据', pres.shapes.PENTAGON, C.panel, C.text], ['物理模型估算', pres.shapes.CHEVRON, C.panel, C.text], ['机器学习纠偏', pres.shapes.CHEVRON, C.cyan, C.dark]]
  .forEach(([t, shp, fill, col], i) => box(s, 56 + i * 234, 440, 250, 68, t, { shape: shp, fill, line: i < 2 ? C.cyan : null, color: col, bold: true, size: 18, align: 'center', valign: 'middle', margin: 0 }));
box(s, 724, 380, 500, 160, [
  br('−53.89%', { size: 96, bold: true, color: C.green }),
  r('测试中平均估计误差降低', { size: 18, color: C.text }),
], { align: 'right', margin: 0 });
box(s, 56, 620, 700, 34, '小组成员：（待填写）　　2026年10月29日', { size: 16, color: C.sub, margin: 0 });

// ---------- 2 问题 ----------
s = pres.addSlide({ masterName: 'CONTENT' }); s.addNotes(notes[2]);
title(s, 'SOC：电池还剩多少电', '问题');
box(s, 56, 112, 780, 34, 'SOC 就是剩余电量百分比，没法直接测，只能用电压、电流、温度推算', { bold: true, color: C.cyan, margin: 0 });
box(s, 56, 160, 744, 124, [
  br('难点一：看电压不准', { size: 18, bold: true, color: C.amber }),
  br('电压会随用电快慢忽高忽低：猛加速时骤降，松开又回升，'), r('所以不能直接把电压当成电量'),
], { fill: C.panel, line: C.line, gap: 8 });
box(s, 56, 298, 744, 124, [
  br('难点二：“记账”会越记越偏', { size: 18, bold: true, color: C.amber }),
  br('安时积分就是给流出的电流记账：起点记错一点，'), r('或电流表有一点偏差，误差都会越积越大'),
], { fill: C.panel, line: C.line, gap: 8 });
box(s, 56, 436, 744, 150, '我们的办法：物理模型估算 + 机器学习纠偏', { fill: C.panel2, line: C.cyan, lineW: 1.5, size: 18, bold: true, color: C.cyan });
box(s, 80, 486, 320, 80, [br('一阶RC + EKF', { size: 18, bold: true, color: C.white }), r('按电池物理规律估算并实时校准', { size: 16, color: C.sub })], { fill: C.panel, line: C.cyan, valign: 'middle', margin: [6, 16, 6, 16] });
arrow(s, 412, 513, 36, 26);
box(s, 460, 486, 316, 80, [br('随机森林', { size: 18, bold: true, color: C.dark }), r('学习 EKF 常犯的错，再帮它改正', { size: 16, color: C.dark })], { fill: C.cyan, valign: 'middle', margin: [6, 16, 6, 16] });
figure(s, 'outputs/figures/Mixed1_inputs_reference.png', 846, 112, 378, 470);
box(s, 846, 594, 378, 34, '实测：电流一直在跳，电量却平稳下降', { size: 18, margin: 0 });

// ---------- 3 数据 ----------
s = pres.addSlide({ masterName: 'CONTENT' }); s.addNotes(notes[3]);
title(s, '数据来源与参考 SOC', '数据');
box(s, 56, 108, 780, 30, '公开的锂电池实测数据：LG 18650HG2 单节电池，25℃ 环境', { bold: true, color: C.cyan, margin: 0 });
box(s, 56, 140, 780, 26, 'Kollmeyer, Naguib, Skells · Mendeley Data v2 · DOI:10.17632/b5mj79w5w9.2 · CC BY 4.0', { size: 16, color: C.sub, margin: 0 });
for (let i = 0; i < 8; i++) {
  const col = i < 4 ? C.cyan : i < 6 ? C.violet : C.green;
  box(s, 56 + i * 94, 180, 86, 54, `Mixed${i + 1}`, { fill: C.panel, line: col, lineW: 1.5, size: 16, bold: true, align: 'center', valign: 'middle', margin: 0 });
}
[['训练 4 条：用来学习', 56, 368, C.cyan], ['验证 2 条：挑选方案', 432, 180, C.violet], ['测试 2 条：期末考试', 620, 180, C.green]]
  .forEach(([t, x, w, col]) => box(s, x, 240, w, 28, t, { size: 16, bold: true, color: col, align: 'center', margin: 0 }));
box(s, 56, 284, 744, 104, [
  r('参考 SOC = 1 − 已放出电量 / 总容量 ', { size: 24, bold: true, color: C.white }), br('2.72639 Ah', { size: 24, bold: true, color: C.cyan }),
  r('当作“标准答案”：从满电开始，用仪器累计的放电量计算', { size: 16, color: C.sub }),
], { fill: C.panel, line: C.line, gap: 6, valign: 'middle' });
[['起点满电', '每次实验前都充满电并静置约1小时，起点可看作100%'],
 ['不许偷看', '按整条记录分组，测试数据绝不用来调参，像考题不提前泄露'],
 ['答案有误差', '参考值是算出来的，不是绝对真值，本身有一定误差']].forEach(([h, b], i) =>
  box(s, 56, 410 + i * 58, 760, 46, [r('■  ', { color: C.cyan, size: 14 }), r(h + '　', { bold: true, color: C.cyan }), r(b)], { valign: 'middle', margin: [0, 4, 0, 4] }));
box(s, 846, 112, 378, 480, '', { fill: C.panel, line: C.cyan, lineW: 1.5 });
box(s, 862, 124, 346, 34, '这些数据分别用来干什么', { size: 16, bold: true, margin: [4, 8, 4, 8], valign: 'middle' });
[['容量测试 551_Cap_1C', '测出电池总容量 2.72639 Ah'], ['慢放电 549_C20DisCh', '得到“电压—电量”对照曲线'], ['脉冲测试 549_HPPC', '测电池内阻等参数（42个脉冲）'],
 ['动态工况 Mixed1–8', '模拟真实使用：训练、验证、测试'], ['充电记录 Charge', '确认每次实验从满电开始']].forEach(([h, b], i) =>
  box(s, 862, 166 + i * 82, 346, 74, [br(h, { size: 16, bold: true, color: C.cyan }), r(b, { size: 16 })], { valign: 'middle', margin: [4, 8, 4, 8], gap: 4 }));

// ---------- 4 RC + EKF ----------
s = pres.addSlide({ masterName: 'CONTENT' }); s.addNotes(notes[4]);
title(s, '第一步：物理模型估算（RC + EKF）', '算法');
box(s, 56, 112, 600, 160, [
  br('电量怎么变：用掉多少电就减多少；极化电压慢慢恢复', { size: 16, bold: true, color: C.cyan }),
  br('SOCₖ = SOCₖ₋₁ − Ī·Δt / (3600·Q)', { size: 22, color: C.white }),
  r('Upₖ = a·Upₖ₋₁ + R₁(1 − a)·Ī，  a = e^(−Δt/τ)', { size: 22, color: C.white }),
], { fill: C.panel, line: C.line, gap: 10 });
box(s, 56, 286, 600, 112, [
  br('电压怎么算：开路电压减去内阻和极化造成的损失', { size: 16, bold: true, color: C.cyan }),
  r('Vₖ = OCV(SOCₖ) − Iₖ·R₀ − Upₖ', { size: 22, color: C.white }),
], { fill: C.panel, line: C.line, gap: 10 });
box(s, 56, 424, 600, 34, 'EKF 像导航：每一步都用实测电压校准', { size: 18, bold: true, margin: 0 });
[['① 按模型预测', 56, 186, C.panel, C.text], ['② 对比实测电压', 284, 170, C.cyan, C.dark], ['③ 按差距修正', 496, 160, C.panel, C.text]]
  .forEach(([t, x, w, fill, col]) => box(s, x, 466, w, 54, t, { fill, line: C.cyan, lineW: 1.5, color: col, bold: true, size: 18, align: 'center', valign: 'middle', margin: 0 }));
arrow(s, 247, 480, 32, 26); arrow(s, 459, 480, 32, 26);
s.addShape(pres.shapes.LINE, { x: px(149), y: px(540), w: px(427), h: 0, line: { color: C.cyan, width: 1.25, dashType: 'dash' } });
s.addShape(pres.shapes.LINE, { x: px(576), y: px(520), w: 0, h: px(20), line: { color: C.cyan, width: 1.25, dashType: 'dash' } });
s.addShape(pres.shapes.LINE, { x: px(149), y: px(520), w: 0, h: px(20), line: { color: C.cyan, width: 1.25, dashType: 'dash', beginArrowType: 'triangle' } });
figure(s, 'outputs/figures/model/ocv_curve.png', 700, 112, 524, 283);
box(s, 700, 402, 524, 30, '“电压—电量”对照曲线（小电流慢放电测得）', { size: 16, color: C.sub, margin: 0 });
[['R₀ 内阻', '17.907', 'mΩ'], ['R₁ 极化电阻', '7.123', 'mΩ'], ['τ 恢复时间常数', '8.771', 's']].forEach(([n, v, u], i) =>
  box(s, 700 + i * 180, 444, 164, 108, [br(n, { size: 16, color: C.sub }), r(v + ' ', { size: 26, bold: true, color: C.cyan }), r(u, { size: 16, bold: true, color: C.cyan })],
    { fill: C.panel, line: C.line, gap: 6, margin: [10, 10, 10, 12] }));
box(s, 700, 564, 524, 30, '由 42 个脉冲测试求得；没考虑温度影响，所以会留下误差', { size: 16, color: C.sub, margin: 0 });

// ---------- 5 随机森林 ----------
s = pres.addSlide({ masterName: 'CONTENT' }); s.addNotes(notes[5]);
title(s, '第二步：机器学习纠偏（随机森林）', '算法');
[['测量', '电压、电流、温度', C.panel, C.cyan, C.white, C.sub], ['EKF', '先给出一个估计', C.panel, C.violet, C.white, C.sub],
 ['7 个输入信息', '只看现在和过去5秒', C.panel, C.cyan, C.white, C.sub], ['随机森林', '预测 EKF 差多少', C.cyan, null, C.dark, C.dark],
 ['融合 SOC', 'EKF 估计 + 修正量', C.green, null, C.dark, C.dark]].forEach(([h, b, fill, line, hc, bc], i) => {
  box(s, 56 + i * 242, 116, 200, 86, [br(h, { size: 18, bold: true, color: hc }), r(b, { size: 16, color: bc })], { fill, line, lineW: 1.5, align: 'center', valign: 'middle', gap: 4, margin: [4, 6, 4, 6] });
  if (i < 4) arrow(s, 56 + i * 242 + 205, 146, 32, 26);
});
box(s, 56, 226, 640, 400, '随机森林最看重哪些信息（重要性，%）', { fill: C.panel, line: C.line, size: 16, bold: true });
const fname = { soc_ekf: 'EKF 估计值', temperature_degC: '表面温度', voltage_residual_v: '电压预测偏差', current_mean_5s_a: '近5秒平均电流',
  voltage_v: '端电压', voltage_change_5s_v: '近5秒电压变化', current_a: '电流' };
const imp = [...importance].reverse();
s.addChart(pres.charts.BAR, [{ name: '重要性', labels: imp.map(x => fname[x.feature]), values: imp.map(x => Number(x.impurity_importance) * 100) }], {
  ...chartBase, x: px(66), y: px(266), w: px(620), h: px(350), barDir: 'bar', chartColors: [C.cyan],
  dataLabelFormatCode: '0.0', valAxisHidden: true, valGridLine: { style: 'none' }, valAxisMaxVal: 56, barGapWidthPct: 45, catAxisLabelFontSize: 12,
});
[['它学什么', '参考 SOC 与 EKF 估计之间的差值'], ['模型规模', '120 棵决策树一起“投票”'], ['怎么防作弊', '4 条学习 → 2 条挑方案 → 固定后才考试'],
 ['不能偷看', '不输入标准答案、累计电量和未来数据'], ['只改结果', '修正只加在输出上，不改 EKF 内部']].forEach(([h, b], i) =>
  box(s, 720, 226 + i * 80, 504, 72, [br(h, { size: 16, bold: true, color: C.cyan }), r(b)], { fill: C.panel, line: C.line, valign: 'middle', gap: 2, margin: [4, 18, 4, 18] }));

// ---------- 6 正常测试 ----------
s = pres.addSlide({ masterName: 'CONTENT' }); s.addNotes(notes[6]);
title(s, [r('测试结果：平均误差降低 ', { color: C.white }), r('53.89%', { color: C.green })], '结论');
figure(s, 'outputs/figures/experiments/normal_552_Mixed7_soc.png', 56, 112, 660, 353);
box(s, 740, 112, 484, 353, '两条测试记录的误差 RMSE（越小越好）', { fill: C.panel, line: C.line, size: 16, bold: true });
s.addChart(pres.charts.BAR, [
  { name: 'EKF', labels: ['Mixed7', 'Mixed8'], values: [mv('552_Mixed7.csv', 'EKF'), mv('552_Mixed8.csv', 'EKF')] },
  { name: 'EKF + 随机森林', labels: ['Mixed7', 'Mixed8'], values: [mv('552_Mixed7.csv', 'EKF_RF'), mv('552_Mixed8.csv', 'EKF_RF')] },
], { ...chartBase, x: px(752), y: px(150), w: px(460), h: px(305), barDir: 'col', barGrouping: 'clustered', chartColors: [C.violet, C.cyan],
  dataLabelFormatCode: '0.000', valAxisMaxVal: 2.5, valAxisMajorUnit: 0.5, showLegend: true, legendPos: 't', barGapWidthPct: 60 });
[[`${sv('normal', 'EKF').toFixed(3)} → ${sv('normal', 'EKF_RF').toFixed(3)}`, '平均误差 RMSE（百分点）', C.cyan, C.cyan],
 [`${sv('normal', 'EKF', 'mae_pp').toFixed(3)} → ${sv('normal', 'EKF_RF', 'mae_pp').toFixed(3)}`, '平均绝对误差 MAE（百分点）', C.cyan, C.line],
 [sv('normal', 'EKF_RF', 'worst_max_abs_error_pp').toFixed(3), '个别时刻的最大误差（百分点）', C.amber, C.line]].forEach(([v, l, col, line], i) =>
  box(s, 56 + i * 396, 486, 376, 128, [br(v, { size: 40, bold: true, color: col }), r(l, { size: 16, color: C.sub })],
    { fill: C.panel, line, lineW: i ? 1 : 1.5, valign: 'middle', gap: 6, margin: [8, 22, 8, 22] }));

// ---------- 7 干扰实验 ----------
s = pres.addSlide({ masterName: 'CONTENT' }); s.addNotes(notes[7]);
title(s, '换个难度再考：干扰实验与简单对照', '结论');
box(s, 56, 112, 660, 340, '三种情况下的平均误差 RMSE（越小越好）', { fill: C.panel, line: C.line, size: 16, bold: true });
const sc = [['normal', '正常'], ['initial_bias', '起点估低10%'], ['measurement_noise', '测量加噪声']];
s.addChart(pres.charts.BAR, [
  { name: 'EKF', labels: sc.map(x => x[1]), values: sc.map(x => sv(x[0], 'EKF')) },
  { name: '加固定修正值', labels: sc.map(x => x[1]), values: sc.map(x => bv(x[0])) },
  { name: 'EKF + 随机森林', labels: sc.map(x => x[1]), values: sc.map(x => sv(x[0], 'EKF_RF')) },
], { ...chartBase, x: px(66), y: px(148), w: px(640), h: px(296), barDir: 'col', barGrouping: 'clustered', chartColors: [C.violet, C.gray, C.cyan],
  dataLabelFormatCode: '0.000', dataLabelFontSize: 11, valAxisMaxVal: 2.5, valAxisMajorUnit: 0.5, showLegend: true, legendPos: 't', barGapWidthPct: 50 });
figure(s, 'outputs/figures/experiments/initial_bias_552_Mixed7_error.png', 740, 112, 484, 262);
box(s, 740, 384, 484, 60, [br('起点估低时的误差曲线：修正后整体更接近 0，'), r('但会有小幅抖动；模型没有重新训练')], { size: 16, color: C.sub, margin: 0 });
[['起点估错', [r('起点故意估低 10%：误差仍降 '), r(`${((1 - sv('initial_bias', 'EKF_RF') / sv('initial_bias', 'EKF')) * 100).toFixed(2)}%`, { bold: true, color: C.green }), br('；'), r('开头第一个点仍差约 4 个百分点')], C.line],
 ['测量有干扰', [r('给电压、电流加随机干扰：误差降 '), r(`${((1 - sv('measurement_noise', 'EKF_RF') / sv('measurement_noise', 'EKF')) * 100).toFixed(2)}%`, { bold: true, color: C.green }), br('；'), r('只试了一次，还需要多次重复验证')], C.line],
 ['简单对照', [br('只给 EKF 加一个固定修正值 1.59pp，'), r('误差就降 '), r(`${((1 - bv('normal') / sv('normal', 'EKF')) * 100).toFixed(1)}%`, { bold: true, color: C.green }), r(`；随机森林再多降约 ${(bv('normal') - sv('normal', 'EKF_RF')).toFixed(2)}pp`)], C.cyan]]
  .forEach(([h, body, line], i) => box(s, 56 + i * 396, 470, 376, 150, [br(h, { size: 18, bold: true, color: C.cyan }), ...body.map(x => ({ text: x.text, options: { ...x.options, fontSize: pt(16) } }))],
    { fill: C.panel, line, lineW: i === 2 ? 1.5 : 1, gap: 8 }));

// ---------- 8 结论 ----------
s = pres.addSlide({ masterName: 'CONTENT' }); s.addNotes(notes[8]);
title(s, '我们的结论', '结论');
box(s, 56, 112, 440, 400, [
  br('两条测试记录上', { size: 18, bold: true, color: C.cyan }),
  br('−53.89%', { size: 76, bold: true, color: C.green }),
  br('平均估计误差降低幅度', { size: 19 }),
  r(`${sv('normal', 'EKF').toFixed(3)} → ${sv('normal', 'EKF_RF').toFixed(3)} `, { size: 34, bold: true, color: C.cyan }), br('pp', { size: 22, bold: true, color: C.cyan }),
  r('平均误差：EKF → EKF + 随机森林', { size: 16, color: C.sub }),
], { fill: C.panel2, line: C.cyan, lineW: 1.5, margin: [20, 22, 20, 22], gap: 14, valign: 'middle' });
[['① 加了干扰也有效', [br('正常、起点估错、测量有干扰三种情况下，'), r('平均误差都降低 '), r('53.71%～54.46%', { bold: true, color: C.green })], C.cyan],
 ['② 主要功劳是“去掉固定偏差”', [r('约 '), r('81%', { bold: true, color: C.green }), r(' 的改善加一个固定修正值就能做到，随机森林再多降约 0.21pp')], C.cyan],
 ['③ 个别时刻仍有误差', [r('最大误差仍约 3.6～4.4 个百分点，修正后的曲线有小抖动')], C.amber]].forEach(([h, body, hc], i) =>
  box(s, 520, 112 + i * 136, 704, 124, [br(h, { size: 18, bold: true, color: hc }), ...body], { fill: C.panel, line: C.line, valign: 'middle', gap: 8, margin: [8, 26, 8, 26] }));
box(s, 56, 532, 1168, 64, [r('适用范围　', { bold: true, color: C.cyan }), r('只在同一节电池、25℃、两条测试记录上验证过；“标准答案”本身也是计算值')],
  { fill: C.panel, line: C.line, valign: 'middle', margin: [0, 26, 0, 26] });

// ---------- 9 意义 ----------
s = pres.addSlide({ masterName: 'ANCHOR' }); s.addNotes(notes[9]);
s.addShape(pres.shapes.OVAL, { x: px(80), y: px(90), w: px(1120), h: px(480), fill: { color: C.cyan, transparency: 90 }, line: { type: 'none' } });
s.addText('这件事有什么用', { x: px(56), y: px(60), w: px(800), h: px(76), fontFace: FONT, fontSize: pt(48), bold: true, color: C.white, margin: 0, valign: 'middle', isTextBox: true });
s.addText(['问题', '数据', '算法', '结论', '意义'].flatMap((l, i) => [r(l, { color: l === '意义' ? C.cyan : C.sub, bold: l === '意义' }), ...(i < 4 ? [r('　')] : [])]),
  { x: px(880), y: px(80), w: px(344), h: px(40), fontFace: FONT, fontSize: pt(18), align: 'right', valign: 'middle', margin: 0, isTextBox: true });
[['应用意义', 'SOC 是电池的“电量表”：\n电动车、手机、储能都靠它\n显示电量、防止过充过放', C.cyan],
 ['方法意义', '物理模型讲道理，\n机器学习补短板；\n再用简单对照检验真实效果', C.line],
 ['实践意义', '从公开数据到最终测试，\n全流程跑通、可以复现；\n按记录分组，杜绝“偷看答案”', C.line]].forEach(([h, b, line], i) =>
  box(s, 56 + i * 396, 150, 376, 200, [br(h, { size: 22, bold: true, color: C.cyan }), r(b)], { fill: C.panel, line, lineW: i ? 1 : 1.5, gap: 10, margin: [16, 24, 16, 24] }));
box(s, 56, 372, 1168, 70, [r('下一步　', { bold: true, color: C.green }), r('用更多电池、温度和老化数据检验 · 多次重复干扰实验 · 让修正结果更平滑')],
  { fill: C.panel2, line: C.cyan, valign: 'middle', margin: [0, 26, 0, 26] });
s.addText('谢谢大家，欢迎提问', { x: px(56), y: px(492), w: px(700), h: px(70), fontFace: FONT, fontSize: pt(34), bold: true, color: C.white, margin: 0, valign: 'middle', isTextBox: true });

pres.writeFile({ fileName: OUT }).then(f => console.log('wrote', f));
