<template>
  <section class="page" data-module="forklift">
    <header class="page-head">
      <div>
        <h2>场车管理</h2>
        <p class="page-desc">
          场内车辆按班组归属到人：只有归属班组的车辆管理员可登记维修、年检与报废，
          只读岗仅可查看，换人必须走交接并留痕。
        </p>
      </div>
      <div class="page-actions">
        <button v-if="store.isAdmin" class="btn primary" type="button" @click="openCreate">登记场内车辆</button>
        <button class="btn" type="button" @click="exportRows">导出场车管理清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>车辆编号</span>
        <input v-model="keyword" placeholder="按车辆编号检索" />
      </label>
      <label class="filter-item">
        <span>车辆状态</span>
        <select v-model="statusFilter">
          <option value="">全部</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>归属班组</span>
        <select v-model="teamFilter">
          <option value="">全部</option>
          <option value="甲班">甲班</option>
          <option value="乙班">乙班</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>归属与责任</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <RouterLink v-if="column === '车辆编号'" class="link" :to="`/forklift/${row.id}`">
              {{ row[column] ?? '—' }}
            </RouterLink>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td>
            <span class="team-tag">{{ row['归属班组'] }} · {{ row['责任人姓名'] }}</span>
            <div v-if="!store.canManage(String(row['归属班组']))" class="cell-hint">{{ noManageHint(row) }}</div>
          </td>
          <td class="row-actions">
            <template v-if="store.canManage(String(row['归属班组'])) && row['status'] !== '已报废'">
              <button
                v-for="action in allowedActions(row)"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
              <RouterLink class="link" :to="`/forklift/${row.id}`">详情/交接</RouterLink>
            </template>
            <template v-else>
              <RouterLink class="link" :to="`/forklift/${row.id}`">查看详情</RouterLink>
            </template>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无符合条件的场内车辆</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条场车管理记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 登记弹窗：入口本身就只对车辆管理员开放 -->
    <div v-if="creating" class="modal-mask" @click.self="creating = false">
      <form class="modal-card" @submit.prevent="submitCreate">
        <h3>登记场内车辆</h3>
        <p class="modal-hint">登记后车辆归属 {{ store.current?.班组 }}，责任人记为 {{ store.current?.姓名 }}。</p>
        <label v-for="field in createFields" :key="field" class="modal-field">
          <span>{{ field }}<em v-if="requiredFields.includes(field)">*</em></span>
          <input v-model="createForm[field]" :required="requiredFields.includes(field)" />
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="creating = false">取消</button>
          <button class="btn primary" type="submit">确认登记</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/forklift'
const columns = ['车辆编号', '车辆类型', '动力类型', '核定载重', '行驶区域', '驾驶员', '年检日期', '车辆状态']
const statuses = ['正常', '维修中', '待年检', '已报废']
const actions = ['安排维修', '安排年检', '申请报废']
const createFields = ['车辆编号', '车辆类型', '动力类型', '核定载重', '行驶区域', '驾驶员', '年检日期']
const requiredFields = ['车辆编号', '车辆类型', '动力类型']

const store = useSessionStore()
const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const teamFilter = ref('')

const stats = computed(() => {
  const count = (status: string) => rows.value.filter((row) => row.status === status).length
  return [
    { label: '正常车辆', value: count('正常') },
    { label: '维修中', value: count('维修中') },
    { label: '待年检', value: count('待年检') },
    { label: '已报废', value: count('已报废') },
  ]
})

const creating = ref(false)
const createError = ref('')
const createForm = reactive<Record<string, string>>({})

function allowedActions(row: Row): string[] {
  // 已在维修中/待年检的车，同状态动作不必重复出现
  return actions.filter((action) => {
    if (action === '安排维修') return row.status !== '维修中'
    if (action === '安排年检') return row.status !== '待年检'
    return true
  })
}

function noManageHint(row: Row): string {
  if (!store.current) return ''
  if (store.isReadOnly) return '只读岗：仅可查看'
  if (store.isAdmin) return `归属${row['归属班组']}，需该班组管理员办理`
  return '仅车辆管理员可办理'
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  teamFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createError.value = ''
  for (const key of Object.keys(createForm)) delete createForm[key]
  creating.value = true
}

async function submitCreate() {
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm } }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    if (!response.ok || !payload.ok) {
      createError.value = payload.message || '登记失败'
      return
    }
    creating.value = false
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '登记失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = (await response.json()) as { ok: boolean; message?: string }
    if (!response.ok || !payload.ok) {
      errorMessage.value = payload.message || '该操作未获授权'
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '场车管理操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (keyword.value) params.set('keyword', keyword.value)
  if (statusFilter.value) params.set('status', statusFilter.value)
  if (teamFilter.value) params.set('team', teamFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('场内车辆列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '场车管理列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.team-tag {
  background: #eff8ff;
  border: 1px solid #b2ddff;
  color: #175cd3;
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 12px;
  white-space: nowrap;
}
.cell-hint {
  color: var(--muted);
  font-size: 11px;
  margin-top: 2px;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(16, 24, 40, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  background: #fff;
  border-radius: 10px;
  padding: 20px 24px;
  width: 420px;
  max-height: 85vh;
  overflow: auto;
}
.modal-card h3 {
  margin: 0 0 4px;
}
.modal-hint {
  color: var(--muted);
  font-size: 12px;
  margin: 0 0 12px;
}
.modal-field {
  display: block;
  margin-bottom: 10px;
  font-size: 13px;
}
.modal-field span {
  display: block;
  margin-bottom: 4px;
  color: #344054;
}
.modal-field em {
  color: #d92d20;
  font-style: normal;
}
.modal-field input,
.modal-field select {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
</style>
