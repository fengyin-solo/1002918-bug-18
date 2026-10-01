<template>
  <section class="page" data-module="forklift">
    <header class="page-head">
      <div>
        <h2>场车管理</h2>
        <p class="page-desc">车辆归属落到「班组 + 责任人」：只有本班组车辆管理员能登记维修、年检与报废，只读岗只能查看，换人走交接留痕。</p>
      </div>
      <div class="page-actions">
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
        <input v-model="statusFilter" placeholder="正常/维修中/待年检/已报废" />
      </label>
      <label class="filter-item">
        <span>归属班组</span>
        <input v-model="teamFilter" placeholder="按归属班组检索" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p class="tip-text" v-if="session.currentUser">
      当前身份：{{ session.currentUser.name }}（{{ session.currentUser.role }}·{{ session.currentUser.team }}）。非本班组车辆的操作会被后端当场驳回并说明缺少的授权。
    </p>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ formatCell(column, row) }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">查看详情</button>
            <template v-for="action in actions" :key="action">
              <button
                v-if="canRunAction(row)"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-if="!canRunAction(row)" class="tip-text">{{ actionHint(row) }}</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无符合条件的场内车辆</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条场车记录</span>
      <span v-if="okMessage" class="ok-text">{{ okMessage }}</span>
      <span v-else-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/forklift'
const columns = ['车辆编号', '车辆类型', '动力类型', '核定载重', '驾驶员', '年检日期', '车辆状态', '归属班组', '责任人']
const actions = ['安排维修', '安排年检', '申请报废']

const router = useRouter()
const session = useSessionStore()

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const okMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const teamFilter = ref('')

const stats = computed(() => [
  { label: '全部车辆', value: total.value },
  { label: '正常车辆', value: rows.value.filter((row) => row['车辆状态'] === '正常').length },
  { label: '维修中', value: rows.value.filter((row) => row['车辆状态'] === '维修中').length },
  { label: '待年检', value: rows.value.filter((row) => row['车辆状态'] === '待年检').length },
])

function formatCell(column: string, row: Row) {
  if (column === '归属班组') {
    return `${row[column] ?? '—'}${isOwner(row) ? '（本组）' : ''}`
  }
  return row[column] ?? '—'
}

function isOwner(row: Row) {
  const user = session.currentUser
  return Boolean(user && user.role === '车辆管理员' && user.team === row['归属班组'])
}

function canRunAction(row: Row) {
  return isOwner(row) && row['车辆状态'] !== '已报废'
}

function actionHint(row: Row) {
  const user = session.currentUser
  if (!user) return ''
  if (row['车辆状态'] === '已报废') return '已报废'
  if (user.role === '只读岗') return '只读，无权操作'
  if (user.role === '车辆管理员' && user.team !== row['归属班组']) return `需${row['归属班组']}管理员`
  if (user.role === '驾驶员') return '驾驶员无权操作'
  return ''
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

function openDetail(row: Row) {
  void router.push({ name: 'forklift-detail', params: { id: String(row.id) } })
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  okMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.detail || payload.message || '场车动作未生效')
    }
    okMessage.value = payload.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '场车操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  okMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  if (teamFilter.value) query.set('team', teamFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('场内车辆列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '场车列表读取失败'
  }
}

onMounted(reload)
</script>
