<template>
  <section class="page" data-module="forklift-detail">
    <header class="page-head">
      <div>
        <h2>场内车辆详情 · {{ entry?.['车辆编号'] ?? '' }}</h2>
        <p class="page-desc">归属、责任人与驾驶员以同一份快照为准；核定载重、年检日期仅本班组车辆管理员可改，换人必须留交接痕迹。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回列表</button>
      </div>
    </header>

    <div v-if="notFound" class="panel error-text">场内车辆不存在或已归档。</div>
    <template v-else-if="entry">
      <div class="panel">
        <p v-if="permissions" class="tip-text">
          当前身份：{{ permissions.user.name }}（{{ permissions.role }}·{{ permissions.team }}）
          <span v-if="permissions.is_readonly" class="badge readonly">只读岗：仅可查看</span>
          <span v-else-if="permissions.can_edit_fields" class="badge owner">本班组车辆管理员：可办理</span>
          <span v-else-if="permissions.can_take_over" class="badge other">外班组车辆管理员：可发起接收归属</span>
          <span v-else class="badge other">无该车操作授权</span>
        </p>
      </div>

      <h3 class="section-title">归属与台账</h3>
      <div class="detail-grid">
        <div v-for="field in readonlyFields" :key="field" class="detail-item">
          <label>{{ field }}</label>
          <div>{{ (entry[field] ?? '—') || '（未定岗）' }}</div>
        </div>
        <div class="detail-item">
          <label>上一责任人</label>
          <div>{{ entry['上一责任人'] ? `${entry['上一责任人']}（原${entry['上一班组']}）` : '—' }}</div>
        </div>
      </div>

      <h3 class="section-title">核定载重 / 年检日期</h3>
      <form class="panel" @submit.prevent="saveFields">
        <div class="panel-row">
          <label>
            核定载重
            <input v-model="fieldForm['核定载重']" :disabled="!permissions?.can_edit_fields" placeholder="如 2.0t" />
          </label>
          <label>
            年检日期
            <input v-model="fieldForm['年检日期']" :disabled="!permissions?.can_edit_fields" type="date" />
          </label>
          <button class="btn primary" type="submit" :disabled="!permissions?.can_edit_fields">保存修改</button>
          <span v-if="!permissions?.can_edit_fields" class="tip-text">仅本班组车辆管理员可修改这两项；只读岗只能查看。</span>
        </div>
      </form>

      <h3 class="section-title">维修 / 年检 / 报废</h3>
      <div class="panel">
        <div class="panel-row">
          <button
            v-for="action in actions"
            :key="action"
            class="btn"
            type="button"
            :disabled="!permissions?.can_run_actions"
            @click="runAction(action)"
          >
            {{ action }}
          </button>
          <span v-if="permissions?.scrapped" class="tip-text">车辆已报废，不能再登记维修、年检或重复报废。</span>
          <span v-else-if="!permissions?.can_run_actions" class="tip-text">
            仅{{ entry['归属班组'] }}车辆管理员可登记维修、年检与报废；代办请求会被后端驳回。
          </span>
        </div>
      </div>

      <h3 class="section-title">换人交接</h3>
      <form class="panel" @submit.prevent="submitHandover">
        <div class="panel-row">
          <label>
            接手驾驶员
            <select v-model="handoverForm.new_driver" :disabled="!canHandover">
              <option value="" disabled>请选择在册驾驶员</option>
              <option v-for="name in driverOptions" :key="name" :value="name">{{ name }}</option>
            </select>
          </label>
          <label>
            转入班组（不选为本班组内交接）
            <select v-model="handoverForm.new_team" :disabled="!canHandover" @change="onTeamChange">
              <option value="">本班组（{{ entry['归属班组'] }}）内部交接</option>
              <option v-for="team in otherTeams" :key="team" :value="team">转入 {{ team }}</option>
            </select>
          </label>
          <label v-if="handoverForm.new_team">
            新责任人（须为转入班组车辆管理员）
            <select v-model="handoverForm.new_owner_id" :disabled="!canHandover">
              <option v-for="admin in targetAdmins" :key="admin.id" :value="admin.id">
                {{ admin.name }}｜{{ admin.title }}
              </option>
            </select>
          </label>
          <label class="tip-text" style="flex:1;min-width:220px">
            交接说明
            <input v-model="handoverForm.remark" :disabled="!canHandover" placeholder="如：转岗 / 班组运力划转" style="width:100%" />
          </label>
          <button class="btn primary" type="submit" :disabled="!canHandover">
            {{ handoverForm.new_team ? '办理归属调整' : '办理驾驶员交接' }}
          </button>
        </div>
        <p class="tip-text" style="margin-bottom:0">
          交接只追加痕迹：原班组「{{ entry['归属班组'] }}」、原责任人「{{ entry['责任人'] }}」记入历史，历史台账仍归原班组。
        </p>
      </form>

      <h3 class="section-title">交接痕迹（{{ handovers.length }}）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in handoverColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in handovers" :key="String(row.id)">
            <td v-for="column in handoverColumns" :key="column">{{ row[column] ?? '—' }}</td>
          </tr>
          <tr v-if="!handovers.length">
            <td :colspan="handoverColumns.length" class="empty-state">暂无交接记录</td>
          </tr>
        </tbody>
      </table>

      <h3 class="section-title">操作台账（{{ logs.length }}）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in logColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in logs" :key="String(row.id)">
            <td v-for="column in logColumns" :key="column">{{ row[column] ?? '—' }}</td>
          </tr>
          <tr v-if="!logs.length">
            <td :colspan="logColumns.length" class="empty-state">暂无操作记录</td>
          </tr>
        </tbody>
      </table>
    </template>

    <footer class="page-foot">
      <span v-if="okMessage" class="ok-text">{{ okMessage }}</span>
      <span v-else-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'
import { useSessionStore, type SessionUser } from '@/stores/session'

type Entry = Record<string, string | number | null>
type LogRow = Record<string, string | number | null>
interface Permissions {
  user: SessionUser
  role: string
  team: string
  is_readonly: boolean
  can_edit_fields: boolean
  can_run_actions: boolean
  can_handover_same_team: boolean
  can_take_over: boolean
  scrapped: boolean
}

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const entryId = String(route.params.id)
const ENDPOINT = `/api/forklift/${entryId}`

const readonlyFields = ['车辆编号', '车辆类型', '动力类型', '核定载重', '行驶区域', '驾驶员', '年检日期', '车辆状态', '归属班组', '责任人']
const actions = ['安排维修', '安排年检', '申请报废']
const handoverColumns = ['交接类型', '原班组', '原责任人', '原驾驶员', '新班组', '新责任人', '新驾驶员', '操作人', '时间', '备注']
const logColumns = ['动作', '明细', '操作人', '操作时班组', '时间']

const entry = ref<Entry | null>(null)
const handovers = ref<LogRow[]>([])
const logs = ref<LogRow[]>([])
const permissions = ref<Permissions | null>(null)
const errorMessage = ref('')
const okMessage = ref('')
const notFound = ref(false)

const fieldForm = reactive<Record<string, string>>({ 核定载重: '', 年检日期: '' })
const handoverForm = reactive({ new_driver: '', new_team: '', new_owner_id: '', remark: '' })

const allTeams = ref<string[]>([])
const driverRoster = ref<Record<string, string[]>>({})

const otherTeams = computed(() => allTeams.value.filter((team) => team !== entry.value?.['归属班组']))
const targetTeam = computed(() => handoverForm.new_team || String(entry.value?.['归属班组'] ?? ''))
const driverOptions = computed(() => driverRoster.value[targetTeam.value] ?? [])
const targetAdmins = computed<SessionUser[]>(() =>
  session.users.filter((user) => user.role === '车辆管理员' && user.team === handoverForm.new_team),
)
// 本班组管理员办内部交接；外班组管理员只能办转入本班组的归属调整。
const canHandover = computed(() => {
  if (!permissions.value || !entry.value) return false
  if (permissions.value.is_readonly || permissions.value.scrapped) return false
  if (handoverForm.new_team) return permissions.value.can_take_over
  return permissions.value.can_handover_same_team
})

function onTeamChange() {
  handoverForm.new_driver = ''
  handoverForm.new_owner_id = targetAdmins.value[0]?.id ?? ''
}

function goBack() {
  void router.push({ name: 'forklift' })
}

async function saveFields() {
  errorMessage.value = ''
  okMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/fields`, {
      method: 'POST',
      body: JSON.stringify({ values: { 核定载重: fieldForm['核定载重'], 年检日期: fieldForm['年检日期'] } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.detail || payload.message || '修改未生效')
    okMessage.value = payload.message
    await loadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '字段修改失败'
  }
}

async function runAction(action: string) {
  errorMessage.value = ''
  okMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.detail || payload.message || '动作未生效')
    okMessage.value = payload.message
    await loadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败'
  }
}

async function submitHandover() {
  errorMessage.value = ''
  okMessage.value = ''
  const values: Record<string, string> = {
    new_driver: handoverForm.new_driver,
    remark: handoverForm.remark,
  }
  if (handoverForm.new_team) {
    values.new_team = handoverForm.new_team
    values.new_owner_id = handoverForm.new_owner_id
  }
  try {
    const response = await request(`${ENDPOINT}/handover`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.detail || payload.message || '交接未生效')
    okMessage.value = payload.message
    handoverForm.new_driver = ''
    handoverForm.new_team = ''
    handoverForm.new_owner_id = ''
    handoverForm.remark = ''
    await loadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '交接失败'
  }
}

async function loadTeams() {
  try {
    const response = await request('/api/forklift/teams')
    if (response.ok) {
      const payload = await response.json()
      allTeams.value = payload.teams ?? []
      driverRoster.value = payload.drivers ?? {}
    }
  } catch {
    // 名册取失败不阻断查看，交接下拉可能为空
  }
}

async function loadAll() {
  errorMessage.value = ''
  try {
    const [detailResp, permResp] = await Promise.all([
      request(`${ENDPOINT}/detail`),
      request(`${ENDPOINT}/permissions`),
    ])
    if (detailResp.status === 404) {
      notFound.value = true
      return
    }
    const detail = await detailResp.json()
    const perm = permResp.ok ? await permResp.json() : null
    entry.value = detail.entry
    handovers.value = detail.handovers ?? []
    logs.value = detail.logs ?? []
    permissions.value = perm
    fieldForm['核定载重'] = String(entry.value?.['核定载重'] ?? '')
    fieldForm['年检日期'] = String(entry.value?.['年检日期'] ?? '')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '车辆详情读取失败'
  }
}

onMounted(() => {
  void loadTeams()
  void loadAll()
})
</script>
