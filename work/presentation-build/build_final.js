// 课堂展示·科技深蓝版：参考主流科技答辩模板（深蓝底 + 单一亮蓝主色 + 金色数字强调），
// 加 01–05 章节页、去掉右上导航；数字全部从结果文件读取。
const fs = require('fs');
const path = require('path');
const { createDeck, notesFrom } = require(process.env.USERPROFILE + '/.claude/skills/classroom-ppt/scripts/ppt_kit.js');

const ROOT = 'D:/document/电气大数据与人工智能';
const OUT = path.join(ROOT, 'presentation/SOC融合估计_课堂展示_最终版.pptx');
const P = rel => path.join(ROOT, rel);

// ---------- 数据 ----------
const csv = f => {
  const [h, ...r] = fs.readFileSync(P(f), 'utf8').trim().split(/\r?\n/);
  const k = h.split(',');
  return r.map(l => Object.fromEntries(l.split(',').map((v, i) => [k[i], v])));
};
const summary = csv('outputs/experiments/summary.csv');
const metrics = csv('outputs/experiments/metrics.csv');
const baseline = csv('outputs/baseline/summary.csv');
const importance = csv('outputs/correction/feature_importance.csv');
const params = JSON.parse(fs.readFileSync(P('outputs/model/battery_parameters.json'), 'utf8'));
const sv = (s, m, k = 'rmse_pp') => Number(summary.find(r => r.scenario === s && r.method === m)[k]);
const mv = (file, m) => Number(metrics.find(r => r.scenario === 'normal' && r.file === file && r.method === m).rmse_pp);
const bv = s => Number(baseline.find(r => r.scenario === s && r.method === 'EKF_offset').rmse_pp);
const drop = s => ((1 - sv(s, 'EKF_RF') / sv(s, 'EKF')) * 100).toFixed(2) + '%';
const HERO = '−' + drop('normal');
const ekfN = sv('normal', 'EKF').toFixed(3), rfN = sv('normal', 'EKF_RF').toFixed(3);

const notes = notesFrom(P('presentation/6分钟讲稿与答辩.md'), 16);
const deck = createDeck({
  title: '锂电池 SOC 融合估计',
  theme: {
    bg: '081A33', panel: '0F2747', panel2: '10345E', line: '1E4170', primary: '3EA6FF', accent: 'FFC24B',
    secondary: '6F8FBF', muted: '5E7899', warn: 'FF8A5B', text: 'E8EFF8', sub: '9DB0C8', title: 'FFFFFF', onPrimary: '06152B', grid: true,
  },
});
const T = deck.theme, { run, line, px, pres } = deck;
// 内容页标题左侧的竖条，模板里常见的“标题锚点”
const page = o => {
  const s = deck.content(o);
  s.slide.addShape(pres.shapes.RECTANGLE, { x: px(36), y: px(52), w: px(6), h: px(40), fill: { color: T.primary }, line: { type: 'none' } });
  return s;
};
const arrow = (s, x, y, w = 32) => s.slide.addShape(pres.shapes.RIGHT_ARROW, { x: px(x), y: px(y), w: px(w), h: px(26), fill: { color: T.primary }, line: { type: 'none' } });

// ---------- 1 封面 ----------
deck.cover({
  course: '电气大数据与人工智能 · 课程项目', title: '锂电池 SOC 融合估计', subtitle: '扩展卡尔曼滤波 + 随机森林误差补偿',
  question: '研究问题：电池忽快忽慢地用电时，怎样准确知道还剩多少电？',
  steps: ['公开实测数据', '物理模型估算', '机器学习纠偏'], hero: { value: HERO, label: '测试中平均估计误差降低' },
  footer: '小组成员：（待填写）　　2026年10月29日', notes: notes[1],
});

// ---------- 目录 ----------
let s = page({ title: '目录', notes: notes[2] });
[['01', '引入问题', ['为什么要估计', '电池还剩多少电']], ['02', '数据来源', ['公开实测数据', '和“标准答案”']], ['03', '展示算法', ['物理模型估算', '+ 机器学习纠偏']],
 ['04', '展示结论', ['测试成绩', '与干扰实验']], ['05', '项目意义', ['有什么用', '下一步做什么']]].forEach(([n, t, d], i) =>
  s.text(56 + i * 238, 170, 216, 380, [line(n, { size: 72, bold: true, color: T.primary }), line(t, { size: 28, bold: true, color: T.title }),
    line(d[0], { size: 18, color: T.sub }), run(d[1], { size: 18, color: T.sub })],
    { fill: T.panel, line: T.line, gap: 10, margin: [36, 24, 24, 26] }));

// ---------- 01 引入问题 ----------
deck.section({ num: '01', title: '引入问题', subtitle: '为什么要估计电池还剩多少电', notes: notes[3] });
s = page({ title: 'SOC：电池还剩多少电', lead: 'SOC 就是剩余电量百分比，没法直接测，只能用电压、电流、温度推算', notes: notes[4] });
s.card(56, 156, 744, 124, { heading: '难点一：看电压不准', headingColor: T.accent, body: '电压会随用电快慢忽高忽低：猛加速时骤降，松开又回升，\n所以不能直接把电压当成电量' });
s.card(56, 294, 744, 124, { heading: '难点二：“记账”会越记越偏', headingColor: T.accent, body: '安时积分就是给流出的电流记账：起点记错一点，\n或电流表有一点偏差，误差都会越积越大' });
s.card(56, 432, 744, 160, { heading: '我们的办法：物理模型估算 + 机器学习纠偏', accent: true, fill: T.panel2 });
s.flow(80, 482, 696, 84, [{ title: '一阶RC + EKF', desc: '按物理规律估算并实时校准' }, { title: '随机森林', desc: '学习 EKF 常犯的错再改正' }]);
s.figure(846, 156, 378, 430, P('outputs/figures/Mixed1_inputs_reference.png'), '实测：电流一直在跳，电量却平稳下降');

// ---------- 02 数据来源 ----------
deck.section({ num: '02', title: '数据来源', subtitle: '公开实测数据 + 怎么得到“标准答案”', notes: notes[5] });
s = page({ title: '数据来源与参考 SOC', lead: '公开的锂电池实测数据：LG 18650HG2 单节电池，25℃ 环境', notes: notes[6] });
s.text(56, 142, 780, 26, 'Kollmeyer, Naguib, Skells · Mendeley Data v2 · DOI:10.17632/b5mj79w5w9.2 · CC BY 4.0', { size: 16, color: T.sub });
for (let i = 0; i < 8; i++) {
  const col = i < 4 ? T.primary : i < 6 ? T.secondary : T.accent;
  s.text(56 + i * 94, 182, 86, 52, `Mixed${i + 1}`, { fill: T.panel, line: col, lineW: 1.5, size: 16, bold: true, align: 'center', valign: 'middle' });
}
[['训练 4 条：用来学习', 56, 368, T.primary], ['验证 2 条：挑选方案', 432, 180, T.secondary], ['测试 2 条：期末考试', 620, 180, T.accent]]
  .forEach(([t, x, w, col]) => s.text(x, 240, w, 28, t, { size: 16, bold: true, color: col, align: 'center' }));
s.card(56, 284, 744, 104, { valign: 'middle', body: [
  run('参考 SOC = 1 − 已放出电量 / 总容量 ', { size: 24, bold: true, color: T.title }), line(`${params.capacity_ah} Ah`, { size: 24, bold: true, color: T.accent }),
  run('当作“标准答案”：从满电开始，用仪器累计的放电量计算', { size: 16, color: T.sub })] });
[['起点满电', '每次实验前都充满电并静置约1小时，起点可看作100%'],
 ['不许偷看', '按整条记录分组，测试数据绝不用来调参，像考题不提前泄露'],
 ['答案有误差', '参考值是算出来的，不是绝对真值，本身有一定误差']].forEach(([h, b], i) =>
  s.text(56, 408 + i * 58, 760, 46, [run('■  ', { size: 16, color: T.primary }), run(h + '　', { bold: true, color: T.primary }), run(b)], { valign: 'middle', margin: [0, 4, 0, 4] }));
s.text(846, 112, 378, 482, '', { fill: T.panel, line: T.primary, lineW: 1.5 });
s.text(862, 124, 346, 34, '这些数据分别用来干什么', { size: 18, bold: true, valign: 'middle', margin: [4, 8, 4, 8] });
[['容量测试 551_Cap_1C', `测出电池总容量 ${params.capacity_ah} Ah`], ['慢放电 549_C20DisCh', '得到“电压—电量”对照曲线'], ['脉冲测试 549_HPPC', '测电池内阻等参数（42个脉冲）'],
 ['动态工况 Mixed1–8', '模拟真实使用：训练、验证、测试'], ['充电记录 Charge', '确认每次实验从满电开始']].forEach(([h, b], i) =>
  s.text(862, 166 + i * 82, 346, 74, [line(h, { size: 16, bold: true, color: T.primary }), run(b, { size: 16 })], { size: 16, valign: 'middle', margin: [4, 8, 4, 8], gap: 4 }));

// ---------- 03 展示算法 ----------
deck.section({ num: '03', title: '展示算法', subtitle: '第一步物理模型估算，第二步机器学习纠偏', notes: notes[7] });
s = page({ title: '第一步：物理模型估算（RC + EKF）', notes: notes[8] });
s.card(56, 112, 600, 160, { body: [
  line('电量怎么变：用掉多少电就减多少；极化电压慢慢恢复', { size: 16, bold: true, color: T.primary }),
  line('SOCₖ = SOCₖ₋₁ − Ī·Δt / (3600·Q)', { size: 22, color: T.title }),
  run('Upₖ = a·Upₖ₋₁ + R₁(1 − a)·Ī，  a = e^(−Δt/τ)', { size: 22, color: T.title })] });
s.card(56, 286, 600, 112, { body: [
  line('电压怎么算：开路电压减去内阻和极化造成的损失', { size: 16, bold: true, color: T.primary }),
  run('Vₖ = OCV(SOCₖ) − Iₖ·R₀ − Upₖ', { size: 22, color: T.title })] });
s.text(56, 424, 600, 34, 'EKF 像导航：每一步都用实测电压校准', { size: 18, bold: true });
s.flow(56, 466, 600, 54, [{ title: '① 按模型预测' }, { title: '② 对比实测电压', highlight: true }, { title: '③ 按差距修正', highlight: false }]);
s.slide.addShape(pres.shapes.LINE, { x: px(147), y: px(540), w: px(418), h: 0, line: { color: T.primary, width: 1.25, dashType: 'dash' } });
s.slide.addShape(pres.shapes.LINE, { x: px(565), y: px(520), w: 0, h: px(20), line: { color: T.primary, width: 1.25, dashType: 'dash' } });
s.slide.addShape(pres.shapes.LINE, { x: px(147), y: px(520), w: 0, h: px(20), line: { color: T.primary, width: 1.25, dashType: 'dash', beginArrowType: 'triangle' } });
s.figure(700, 112, 524, 283, P('outputs/figures/model/ocv_curve.png'));
s.text(700, 402, 524, 30, '“电压—电量”对照曲线（小电流慢放电测得）', { size: 16, color: T.sub });
[['R₀ 内阻', (params.r0_ohm * 1000).toFixed(3), 'mΩ'], ['R₁ 极化电阻', (params.r1_ohm * 1000).toFixed(3), 'mΩ'], ['τ 恢复时间常数', params.tau_s.toFixed(3), 's']].forEach(([n, v, u], i) =>
  s.text(700 + i * 180, 444, 164, 108, [run(v + ' ', { size: 26, bold: true, color: T.primary }), line(u, { size: 16, bold: true, color: T.primary }), run(n, { size: 16, color: T.sub })],
    { fill: T.panel, line: T.line, valign: 'middle', gap: 6, margin: [8, 10, 8, 12] }));
s.text(700, 564, 524, 30, '由 42 个脉冲测试求得；没考虑温度影响，所以会留下误差', { size: 16, color: T.sub });

s = page({ title: '第二步：机器学习纠偏（随机森林）', notes: notes[9] });
s.flow(56, 116, 1168, 86, [{ title: '测量', desc: '电压、电流、温度' }, { title: 'EKF', desc: '先给出一个估计' }, { title: '7 个输入信息', desc: '只看现在和过去5秒' },
  { title: '随机森林', desc: '预测 EKF 差多少', highlight: true }, { title: '融合 SOC', desc: 'EKF 估计 + 修正量' }]);
const fname = { soc_ekf: 'EKF 估计值', temperature_degC: '表面温度', voltage_residual_v: '电压预测偏差', current_mean_5s_a: '近5秒平均电流',
  voltage_v: '端电压', voltage_change_5s_v: '近5秒电压变化', current_a: '电流' };
const imp = [...importance].reverse();
s.bars(56, 226, 640, 400, { heading: '随机森林最看重哪些信息（重要性，%）', horizontal: true, format: '0.0', max: 56, colors: [T.primary],
  categories: imp.map(x => fname[x.feature]), series: [{ name: '重要性', values: imp.map(x => Number(x.impurity_importance) * 100) }] });
[['它学什么', '参考 SOC 与 EKF 估计之间的差值'], ['模型规模', '120 棵决策树一起“投票”'], ['怎么防作弊', '4 条学习 → 2 条挑方案 → 固定后才考试'],
 ['不能偷看', '不输入标准答案、累计电量和未来数据'], ['只改结果', '修正只加在输出上，不改 EKF 内部']].forEach(([h, b], i) =>
  s.text(720, 226 + i * 80, 504, 72, [line(h, { size: 16, bold: true, color: T.primary }), run(b)], { fill: T.panel, line: T.line, valign: 'middle', gap: 2, margin: [4, 18, 4, 18] }));

// ---------- 04 展示结论 ----------
deck.section({ num: '04', title: '展示结论', subtitle: '期末考试成绩、换难度再考、最终结论', notes: notes[10] });
s = page({ title: [run('测试结果：平均误差降低 ', { color: T.title }), run(drop('normal'), { color: T.accent })], notes: notes[11] });
s.figure(56, 112, 660, 353, P('outputs/figures/experiments/normal_552_Mixed7_soc.png'));
s.bars(740, 112, 484, 353, { heading: '两条测试记录的误差 RMSE（越小越好）', format: '0.000', max: 2.5, categories: ['Mixed7', 'Mixed8'], series: [
  { name: 'EKF', values: [mv('552_Mixed7.csv', 'EKF'), mv('552_Mixed8.csv', 'EKF')] },
  { name: 'EKF + 随机森林', values: [mv('552_Mixed7.csv', 'EKF_RF'), mv('552_Mixed8.csv', 'EKF_RF')] }] });
s.kpi(56, 486, 376, 128, { value: `${ekfN} → ${rfN}`, label: '平均误差 RMSE（百分点）', accent: true, color: T.accent });
s.kpi(452, 486, 376, 128, { value: `${sv('normal', 'EKF', 'mae_pp').toFixed(3)} → ${sv('normal', 'EKF_RF', 'mae_pp').toFixed(3)}`, label: '平均绝对误差 MAE（百分点）' });
s.kpi(848, 486, 376, 128, { value: sv('normal', 'EKF_RF', 'worst_max_abs_error_pp').toFixed(3), label: '个别时刻的最大误差（百分点）', color: T.warn });

s = page({ title: '换个难度再考：干扰实验与简单对照', notes: notes[12] });
const sc = [['normal', '正常'], ['initial_bias', '起点估低10%'], ['measurement_noise', '测量加噪声']];
s.bars(56, 112, 660, 340, { heading: '三种情况下的平均误差 RMSE（越小越好）', format: '0.000', max: 2.5, colors: [T.secondary, T.muted, T.primary], categories: sc.map(x => x[1]), series: [
  { name: 'EKF', values: sc.map(x => sv(x[0], 'EKF')) }, { name: '加固定修正值', values: sc.map(x => bv(x[0])) }, { name: 'EKF + 随机森林', values: sc.map(x => sv(x[0], 'EKF_RF')) }] });
s.figure(740, 112, 484, 262, P('outputs/figures/experiments/initial_bias_552_Mixed7_error.png'));
s.text(740, 384, 484, 60, '起点估低时的误差曲线：修正后整体更接近 0，\n但会有小幅抖动；模型没有重新训练', { size: 16, color: T.sub });
const g = t => run(t, { size: 16, bold: true, color: T.accent }), n16 = t => run(t, { size: 16 }), b16 = t => line(t, { size: 16 });
[['起点估错', [n16('起点故意估低 10%：误差仍降 '), g(drop('initial_bias')), b16('；'), n16('开头第一个点仍差约 4 个百分点')], false],
 ['测量有干扰', [n16('给电压、电流加随机干扰：误差降 '), g(drop('measurement_noise')), b16('；'), n16('只试了一次，还需要多次重复验证')], false],
 ['简单对照', [b16('只给 EKF 加一个固定修正值 1.59pp，'), n16('误差就降 '), g(`${((1 - bv('normal') / sv('normal', 'EKF')) * 100).toFixed(1)}%`),
   n16(`；随机森林再多降约 ${(bv('normal') - sv('normal', 'EKF_RF')).toFixed(2)}pp`)], true]]
  .forEach(([h, body, accent], i) => s.card(56 + i * 396, 470, 376, 150, { heading: h, body, accent, size: 16 }));

s = page({ title: '我们的结论', notes: notes[13] });
s.text(56, 112, 440, 400, [
  line('两条测试记录上', { size: 18, bold: true, color: T.primary }), line(HERO, { size: 76, bold: true, color: T.accent }), line('平均估计误差降低幅度'),
  run(`${ekfN} → ${rfN} `, { size: 34, bold: true, color: T.primary }), line('pp', { size: 22, bold: true, color: T.primary }),
  run('平均误差：EKF → EKF + 随机森林', { size: 16, color: T.sub })], { fill: T.panel2, line: T.primary, lineW: 1.5, margin: [20, 22, 20, 22], gap: 14, valign: 'middle' });
const pct = ['normal', 'initial_bias', 'measurement_noise'].map(x => (1 - sv(x, 'EKF_RF') / sv(x, 'EKF')) * 100);
const share = ((sv('normal', 'EKF') - bv('normal')) / (sv('normal', 'EKF') - sv('normal', 'EKF_RF')) * 100).toFixed(0);
[['① 加了干扰也有效', [line('正常、起点估错、测量有干扰三种情况下，'), run('平均误差都降低 '), run(`${Math.min(...pct).toFixed(2)}%～${Math.max(...pct).toFixed(2)}%`, { bold: true, color: T.accent })], T.primary],
 ['② 主要功劳是“去掉固定偏差”', [run('约 '), run(share + '%', { bold: true, color: T.accent }), run(` 的改善加一个固定修正值就能做到，随机森林再多降约 ${(bv('normal') - sv('normal', 'EKF_RF')).toFixed(2)}pp`)], T.primary],
 ['③ 个别时刻仍有误差', [run('最大误差仍约 3.6～4.4 个百分点，修正后的曲线有小抖动')], T.warn]].forEach(([h, body, hc], i) =>
  s.card(520, 112 + i * 136, 704, 124, { heading: h, headingColor: hc, body, valign: 'middle' }));
s.text(56, 532, 1168, 64, [run('适用范围　', { bold: true, color: T.primary }), run('只在同一节电池、25℃、两条测试记录上验证过；“标准答案”本身也是计算值')],
  { fill: T.panel, line: T.line, valign: 'middle', margin: [0, 26, 0, 26] });

// ---------- 05 项目意义 ----------
deck.section({ num: '05', title: '项目意义', subtitle: '这件事有什么用，下一步做什么', notes: notes[14] });
s = page({ title: '这件事有什么用', notes: notes[15] });
[['应用意义', 'SOC 是电池的“电量表”：\n电动车、手机、储能都靠它\n显示电量、防止过充过放', true],
 ['方法意义', '物理模型讲道理，\n机器学习补短板；\n再用简单对照检验真实效果', false],
 ['实践意义', '从公开数据到最终测试，\n全流程跑通、可以复现；\n按记录分组，杜绝“偷看答案”', false]].forEach(([h, b, accent], i) =>
  s.text(56 + i * 396, 120, 376, 250, [line(h, { size: 26, bold: true, color: T.primary }), ...b.split('\n').map((t, j, a) => j < a.length - 1 ? line(t, { size: 20 }) : run(t, { size: 20 }))],
    { fill: T.panel, line: accent ? T.primary : T.line, lineW: accent ? 1.5 : 1, gap: 14, margin: [26, 28, 22, 28] }));
s.text(56, 402, 1168, 40, '下一步可以做什么', { size: 24, bold: true, color: T.accent });
[['更多数据', '用更多电池、温度\n和老化数据检验'], ['重复实验', '干扰实验多做几次，\n确认结论站得住'], ['更平滑', '让修正后的曲线\n少一点抖动']].forEach(([h, b], i) =>
  s.card(56 + i * 396, 456, 376, 140, { heading: h, headingColor: T.accent, body: b, fill: T.panel2 }));

deck.ending({ subtitle: '锂电池 SOC 融合估计 · EKF + 随机森林误差补偿', notes: notes[16] });
deck.save(OUT).then(f => console.log('wrote', f));
