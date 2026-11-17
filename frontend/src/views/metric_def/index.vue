<template>
  <section class="page" data-module="metric_def">
    <header class="page-head">
      <div><h2>指标定义</h2><p class="page-desc">维护指标，围绕指标编号、指标名称、计算公式、统计粒度做登记、筛选与状态流转；发布后按口径版本重算指标结果。</p></div>
    </header>
    <div class="analysis-summary">
      <article v-for="m in summaryMetrics" :key="m.label" class="analysis-card" data-testid="kpi-card">
        <span style="font-size:12px;color:var(--muted)">{{ m.label }}</span>
        <strong style="font-size:22px;display:block">{{ m.value }}</strong>
        <span :class="m.trend > 0 ? 'trend-up' : 'trend-down'" style="font-size:12px">{{ m.trend > 0 ? '↑' : '↓' }}{{ Math.abs(m.trend) }}%</span>
      </article>
    </div>
    <form class="analysis-form" @submit.prevent="runAnalysis">
      <label v-for="field in paramFields" :key="field"><span>{{ field }}</span>
        <select v-if="field.includes('方法')||field.includes('策略')||field.includes('粒度')" v-model="params[field]"><option v-for="o in options[field]" :key="o" :value="o">{{ o }}</option></select>
        <input v-else v-model="params[field]" :placeholder="`请输入${field}`" />
      </label>
      <button class="btn primary" type="submit" data-testid="run-analysis">运行分析</button>
    </form>
    <div v-if="chartData.length" class="analysis-chart">
      <div v-for="(bar, i) in chartData" :key="i" class="analysis-bar" :style="{ height: barHeight(bar.value) + 'px' }"><span>{{ bar.label }}</span></div>
    </div>
    <table class="data-table" v-if="results.length">
      <thead><tr><th v-for="c in resultColumns" :key="c">{{ c }}</th></tr></thead>
      <tbody><tr v-for="row in results" :key="row.id"><td v-for="c in resultColumns" :key="c">{{ row[c] ?? '—' }}</td></tr></tbody>
    </table>
    <p v-if="!results.length && !loading" style="text-align:center;color:var(--muted)">请配置参数后运行分析</p>

    <section class="block" data-testid="metric-publish-section">
      <h3 class="block-title">指标口径与发布</h3>
      <p class="block-desc">修改草稿的统计粒度或计算公式后，历史发布记录仍保留旧口径数值；发布前可重新校验公式并按当前口径版本预览重算结果。</p>
      <table class="data-table">
        <thead>
          <tr><th>指标编号</th><th>指标名称</th><th>状态</th><th>统计粒度</th><th>计算公式</th><th>口径版本</th><th>指标值</th><th>对比基准</th><th>差异</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="m in metrics" :key="m.id" :data-testid="`metric-row-${m.id}`">
            <td>{{ m.指标编号 }}</td>
            <td>{{ m.指标名称 }}</td>
            <td>{{ m.status }}</td>
            <td>
              <select v-model="draftEdits[m.id].统计粒度" :disabled="m.status === '已废弃'" :data-testid="`granularity-${m.id}`">
                <option v-for="g in granularityOptionsFor(m)" :key="g" :value="g">{{ g }}</option>
              </select>
            </td>
            <td><input v-model="draftEdits[m.id].计算公式" :disabled="m.status === '已废弃'" :data-testid="`formula-${m.id}`" /></td>
            <td>{{ m.口径版本 }}</td>
            <td>{{ m.指标值 }}</td>
            <td>{{ m.对比基准 }}</td>
            <td>{{ m.差异 }}</td>
            <td class="row-actions">
              <button class="link" type="button" :disabled="m.status === '已废弃'" :data-testid="`save-draft-${m.id}`" @click="saveDraft(m)">保存草稿</button>
              <button class="link" type="button" :disabled="m.status === '已废弃'" :data-testid="`publish-${m.id}`" @click="publishMetric(m)">发布指标</button>
              <button class="link" type="button" :data-testid="`revalidate-${m.id}`" @click="revalidate(m)">重新校验公式</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="revalidateResult" class="block-hint" data-testid="revalidate-result">{{ revalidateResult }}</p>
    </section>

    <section class="block" data-testid="publish-records-section">
      <h3 class="block-title">历史发布记录</h3>
      <p class="block-desc">每次发布生成可追溯版本，数值按各自来源输入与口径版本重算，修改粒度后历史记录仍保留旧口径结果。</p>
      <table class="data-table">
        <thead>
          <tr><th>版本</th><th>指标编号</th><th>口径版本</th><th>统计粒度</th><th>计算公式</th><th>指标值</th><th>对比基准</th><th>差异</th><th>当前采用</th><th>状态</th><th>发布时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="p in publishes" :key="p.id" :data-testid="`publish-row-${p.id}`">
            <td>V{{ p.版本序号 }}</td>
            <td>{{ p.指标编号 }}</td>
            <td>{{ p.口径版本 }}</td>
            <td>{{ p.统计粒度 }}</td>
            <td>{{ p.计算公式 }}</td>
            <td>{{ p.指标值 }}</td>
            <td>{{ p.对比基准 }}</td>
            <td>{{ p.差异 }}</td>
            <td>{{ p.当前采用 ? '是' : '否' }}</td>
            <td>{{ p.状态 }}</td>
            <td>{{ p.发布时间 }}</td>
          </tr>
          <tr v-if="!publishes.length"><td colspan="11" class="empty-state">暂无发布记录，可先在上方发布指标</td></tr>
        </tbody>
      </table>
    </section>

    <section class="block" data-testid="correction-section">
      <h3 class="block-title">指标纠错</h3>
      <p class="block-desc">选择历史发布记录并指定新的口径版本，同一次纠错中确定引用关系；报错、不生效或丢失的记录也会写入纠错记录并说明不一致原因。重复提交不会生成第二份确认结果。</p>
      <form class="analysis-form" @submit.prevent="submitCorrection">
        <label><span>发布记录</span>
          <select v-model="correctionForm.发布记录id" data-testid="correction-publish">
            <option value="" disabled>请选择发布记录</option>
            <option v-for="p in publishes" :key="p.id" :value="String(p.id)">{{ p.指标编号 }} · V{{ p.版本序号 }}（{{ p.口径版本 }}）{{ p.当前采用 ? ' · 当前采用' : '' }}</option>
          </select>
        </label>
        <label><span>新口径版本</span><input v-model="correctionForm.新口径版本" data-testid="correction-version" placeholder="如 V2.0" /></label>
        <label><span>处理路径</span>
          <select v-model="correctionForm.处理路径" data-testid="correction-path">
            <option v-for="path in correctionPaths" :key="path" :value="path">{{ path }}</option>
          </select>
        </label>
        <button class="btn primary" type="submit" data-testid="submit-correction">提交纠错</button>
      </form>
      <p v-if="correctionMessage" class="block-hint" data-testid="correction-message">{{ correctionMessage }}</p>
      <table class="data-table">
        <thead>
          <tr><th>ID</th><th>指标编号</th><th>发布版本</th><th>处理路径</th><th>新口径版本</th><th>修正前差异</th><th>修正后差异</th><th>不一致原因</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="c in corrections" :key="c.id" :data-testid="`correction-row-${c.id}`">
            <td>{{ c.id }}</td>
            <td>{{ c.指标编号 || '—' }}</td>
            <td>{{ c.发布版本序号 ? `V${c.发布版本序号}` : '—' }}</td>
            <td>{{ c.处理路径 }}</td>
            <td>{{ c.新口径版本 }}</td>
            <td>{{ valueOf(c.修正前, '差异') }}</td>
            <td>{{ valueOf(c.修正后, '差异') }}</td>
            <td>{{ c.不一致原因 || '—' }}</td>
            <td>{{ c.状态 }}</td>
            <td><button class="link" type="button" :data-testid="`correction-detail-${c.id}`" @click="openCorrectionDetail(c)">详情</button></td>
          </tr>
          <tr v-if="!corrections.length"><td colspan="10" class="empty-state">暂无纠错记录</td></tr>
        </tbody>
      </table>
    </section>

    <div v-if="correctionDetail" class="modal-backdrop" data-testid="correction-detail" @click.self="correctionDetail = null">
      <div class="modal">
        <h3>纠错记录详情 #{{ correctionDetail.id }}</h3>
        <dl class="detail-grid">
          <dt>指标编号</dt><dd>{{ correctionDetail.指标编号 || '—' }}</dd>
          <dt>处理路径</dt><dd>{{ correctionDetail.处理路径 }}</dd>
          <dt>新口径版本</dt><dd>{{ correctionDetail.新口径版本 }}</dd>
          <dt>修正范围</dt><dd>{{ correctionDetail.修正范围 }}</dd>
          <dt>状态</dt><dd>{{ correctionDetail.状态 }}（{{ correctionDetail.复核状态 }}）</dd>
          <dt>不一致原因</dt><dd>{{ correctionDetail.不一致原因 || '—' }}</dd>
          <dt>对照结果</dt><dd data-testid="correction-compare">{{ correctionDetail.对照结果 }}</dd>
        </dl>
        <h4>来源输入</h4>
        <table class="data-table">
          <tbody>
            <tr v-for="(v, k) in correctionDetail.来源输入" :key="k"><td>{{ k }}</td><td>{{ v }}</td></tr>
            <tr v-if="!Object.keys(correctionDetail.来源输入 || {}).length"><td class="empty-state">来源输入缺失</td></tr>
          </tbody>
        </table>
        <h4>修正前后数值</h4>
        <table class="data-table">
          <thead><tr><th></th><th>指标值</th><th>对比基准</th><th>差异</th></tr></thead>
          <tbody>
            <tr><td>修正前</td><td>{{ valueOf(correctionDetail.修正前, '指标值') }}</td><td>{{ valueOf(correctionDetail.修正前, '对比基准') }}</td><td>{{ valueOf(correctionDetail.修正前, '差异') }}</td></tr>
            <tr><td>修正后</td><td>{{ valueOf(correctionDetail.修正后, '指标值') }}</td><td>{{ valueOf(correctionDetail.修正后, '对比基准') }}</td><td>{{ valueOf(correctionDetail.修正后, '差异') }}</td></tr>
            <tr v-if="correctionDetail.对照重算"><td>对照重算</td><td>{{ valueOf(correctionDetail.对照重算, '指标值') }}</td><td>{{ valueOf(correctionDetail.对照重算, '对比基准') }}</td><td>{{ valueOf(correctionDetail.对照重算, '差异') }}</td></tr>
          </tbody>
        </table>
        <h4>差异明细（{{ (correctionDetail.差异明细 || []).length }} 条）</h4>
        <table class="data-table">
          <thead><tr><th>发布记录</th><th>版本</th><th>修正前差异</th><th>修正后差异</th></tr></thead>
          <tbody>
            <tr v-for="d in correctionDetail.差异明细" :key="d.发布记录id">
              <td>#{{ d.发布记录id }}</td><td>V{{ d.版本序号 }}</td>
              <td>{{ valueOf(d.修正前, '差异') }}</td><td>{{ valueOf(d.修正后, '差异') }}</td>
            </tr>
            <tr v-if="!(correctionDetail.差异明细 || []).length"><td colspan="4" class="empty-state">无差异明细</td></tr>
          </tbody>
        </table>
        <div class="page-actions" style="margin-top:12px">
          <button class="btn" type="button" data-testid="correction-detail-close" @click="correctionDetail = null">关闭</button>
        </div>
      </div>
    </div>

    <section class="block" data-testid="diff-section">
      <h3 class="block-title">指标差异复核</h3>
      <p class="block-desc">差异接口消费指标纠错记录，展示修正前后数值与当前采用的发布版本，复核后标记对应记录。</p>
      <table class="data-table">
        <thead>
          <tr><th>纠错ID</th><th>指标编号</th><th>处理路径</th><th>修正前指标值</th><th>修正前差异</th><th>修正后指标值</th><th>修正后差异</th><th>当前采用发布版本</th><th>不一致原因</th><th>复核状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="d in diffs" :key="d.纠错id" :data-testid="`diff-row-${d.纠错id}`">
            <td>{{ d.纠错id }}</td>
            <td>{{ d.指标编号 || '—' }}</td>
            <td>{{ d.处理路径 }}</td>
            <td>{{ valueOf(d.修正前, '指标值') }}</td>
            <td>{{ valueOf(d.修正前, '差异') }}</td>
            <td>{{ valueOf(d.修正后, '指标值') }}</td>
            <td>{{ valueOf(d.修正后, '差异') }}</td>
            <td>{{ d.当前采用发布版本 }}</td>
            <td>{{ d.不一致原因 || '—' }}</td>
            <td>{{ d.复核状态 }}</td>
            <td>
              <button v-if="d.状态 === '已确认' && d.复核状态 !== '已复核'" class="link" type="button" :data-testid="`review-${d.纠错id}`" @click="reviewDiff(d)">复核</button>
              <span v-else>—</span>
            </td>
          </tr>
          <tr v-if="!diffs.length"><td colspan="11" class="empty-state">暂无指标差异记录</td></tr>
        </tbody>
      </table>
    </section>

    <footer class="page-foot">
      <span v-if="actionMessage" class="error-text" data-testid="action-message">{{ actionMessage }}</span>
    </footer>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { request } from '@/api/client'

type Row = Record<string, any>

const ENDPOINT = '/api/metric_def'
const summaryMetrics = ref<{label:string;value:number;trend:number}[]>([])
const results = ref<any[]>([]); const chartData = ref<{label:string;value:number}[]>([])
const loading = ref(false)
const params = ref<Record<string,string>>({})
const paramFields = ["指标编号", "指标名称", "计算公式", "统计粒度", "时间窗口", "筛选条件", "精度位数", "口径版本"].filter((f: string) => !['编号','名称','版本'].includes(f)).slice(0, 4)
const options: Record<string,string[]> = { '统计粒度': ['按日','按周','按月'], '分组字段': ['全量','按类型','按区域'], '比较方法': ['环比','同比','绝对值'], '时间范围': ['最近7天','最近30天','最近90天'] }
const resultColumns = computed(() => ["指标编号", "指标名称", "计算公式", "统计粒度", "时间窗口", "筛选条件", "精度位数", "口径版本"].slice(0, 5))

const metrics = ref<Row[]>([])
const publishes = ref<Row[]>([])
const corrections = ref<Row[]>([])
const diffs = ref<Row[]>([])
const draftEdits = ref<Record<string, { 统计粒度: string; 计算公式: string }>>({})
const granularityOptions = ['按日', '按周', '按月']
const correctionPaths = ['采用新草稿', '回滚旧发布']
const correctionForm = ref({ 发布记录id: '', 新口径版本: '', 处理路径: '采用新草稿' })
const correctionMessage = ref('')
const correctionDetail = ref<Row | null>(null)
const revalidateResult = ref('')
const actionMessage = ref('')

function barHeight(v: number) { const max = Math.max(...chartData.value.map(d => d.value), 1); return Math.max(10, (v / max) * 140) }
function valueOf(obj: any, key: string) { return obj && obj[key] !== undefined && obj[key] !== null && obj[key] !== '' ? obj[key] : '—' }
function granularityOptionsFor(m: Row) {
  const current = String(m.统计粒度 ?? '')
  return granularityOptions.includes(current) ? granularityOptions : [current, ...granularityOptions]
}

async function fetchSummary() { try { const res = await request(`${ENDPOINT}/summary`); summaryMetrics.value = (await res.json()).metrics || [] } catch(e) {} }
async function runAnalysis() {
  loading.value = true
  try { const res = await request(`${ENDPOINT}/run`, { method: 'POST', body: JSON.stringify({ values: params.value }) }); const data = await res.json(); results.value = data.items || []; chartData.value = (data.items || []).map((r: any) => ({ label: Object.values(r)[0] as string, value: Object.values(r).filter(v => typeof v === 'number')[0] as number || 0 })).slice(0, 6) } catch(e) { results.value = [] }
  loading.value = false
}

async function readPayload(res: Response) { return res.json().catch(() => ({})) }

async function reloadAll() {
  try {
    const [metricRes, publishRes, correctionRes, diffRes] = await Promise.all([
      request(ENDPOINT), request(`${ENDPOINT}/publishes`), request(`${ENDPOINT}/corrections`), request(`${ENDPOINT}/diffs`),
    ])
    const metricItems = ((await metricRes.json()).items || []) as Row[]
    const publishItems = ((await publishRes.json()).items || []) as Row[]
    const correctionItems = ((await correctionRes.json()).items || []) as Row[]
    const diffItems = ((await diffRes.json()).items || []) as Row[]
    const edits: Record<string, { 统计粒度: string; 计算公式: string }> = {}
    for (const m of metricItems) {
      edits[String(m.id)] = { 统计粒度: String(m.统计粒度 ?? ''), 计算公式: String(m.计算公式 ?? '') }
    }
    // 所有响应式数据在同一个同步块里赋值，避免表格渲染到一半时草稿映射还没就绪
    metrics.value = metricItems
    publishes.value = publishItems
    corrections.value = correctionItems
    diffs.value = diffItems
    draftEdits.value = edits
  } catch (e) {
    actionMessage.value = e instanceof Error ? e.message : '指标数据加载失败'
  }
}

async function saveDraft(m: Row) {
  actionMessage.value = ''
  try {
    const res = await request(`${ENDPOINT}/${m.id}/draft`, { method: 'PUT', body: JSON.stringify({ values: draftEdits.value[String(m.id)] }) })
    const payload = await readPayload(res)
    actionMessage.value = payload.message || '草稿已保存'
    await reloadAll()
  } catch (e) { actionMessage.value = e instanceof Error ? e.message : '草稿保存失败' }
}

async function publishMetric(m: Row) {
  actionMessage.value = ''
  try {
    const res = await request(`${ENDPOINT}/${m.id}/publish`, { method: 'POST' })
    const payload = await readPayload(res)
    actionMessage.value = payload.message || '发布完成'
    await reloadAll()
  } catch (e) { actionMessage.value = e instanceof Error ? e.message : '发布失败' }
}

async function revalidate(m: Row) {
  actionMessage.value = ''
  try {
    const res = await request(`${ENDPOINT}/${m.id}/revalidate`, { method: 'POST' })
    const payload = await readPayload(res)
    const preview = payload.重算预览 ? `指标值 ${payload.重算预览.指标值} / 差异 ${payload.重算预览.差异}` : '无'
    const adopted = payload.当前采用版本 ? `当前采用 ${payload.当前采用版本}` : '暂无发布记录'
    const conflict = payload.草稿与发布冲突 ? '，草稿与发布记录冲突，需提交纠错' : ''
    revalidateResult.value = `${m.指标编号}：${payload.校验说明}；重算预览 ${preview}；${adopted}${conflict}`
  } catch (e) { revalidateResult.value = e instanceof Error ? e.message : '公式校验失败' }
}

async function submitCorrection() {
  correctionMessage.value = ''
  if (!correctionForm.value.发布记录id) { correctionMessage.value = '请选择发布记录'; return }
  try {
    const res = await request(`${ENDPOINT}/corrections`, { method: 'POST', body: JSON.stringify({ values: { ...correctionForm.value } }) })
    const payload = await readPayload(res)
    correctionMessage.value = payload.message || '纠错已提交'
    await reloadAll()
  } catch (e) { correctionMessage.value = e instanceof Error ? e.message : '纠错提交失败' }
}

async function openCorrectionDetail(c: Row) {
  try {
    const res = await request(`${ENDPOINT}/corrections/${c.id}`)
    correctionDetail.value = await res.json()
  } catch (e) { actionMessage.value = e instanceof Error ? e.message : '纠错详情读取失败' }
}

async function reviewDiff(d: Row) {
  actionMessage.value = ''
  try {
    const res = await request(`${ENDPOINT}/diffs/${d.纠错id}/review`, { method: 'POST' })
    const payload = await readPayload(res)
    actionMessage.value = payload.message || '复核完成'
    await reloadAll()
  } catch (e) { actionMessage.value = e instanceof Error ? e.message : '复核失败' }
}

onMounted(() => { fetchSummary(); reloadAll() })
</script>
