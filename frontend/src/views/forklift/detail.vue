<template>
  <section class="page detail-page" data-module="forklift-detail">
    <header class="page-head">
      <div>
        <h2>车辆详情 · {{ entry?.['车辆编号'] ?? '—' }}</h2>
        <p class="page-desc">
          归属：<strong>{{ entry?.['归属班组'] ?? '—' }} · {{ entry?.['责任人姓名'] ?? '—' }}</strong>
          ｜核定载重、年检日期等技术档案仅归属班组车辆管理员可改，只读岗仅可查看。
        </p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/forklift">返回列表</RouterLink>
      </div>
    </header>

    <div v-if="notFound" class="error-text">车辆不存在或已归档。</div>
    <template v-else-if="entry">
      <div v-if="banner" class="banner" :class="bannerOk ? 'ok' : 'deny'">{{ banner }}</div>

      <!-- 基础档案：管理员才渲染可编辑控件，其余身份一律纯文本 -->
      <article class="detail-card">
        <h3>车辆档案</h3>
        <div v-if="canManage" class="edit-grid">
          <label v-for="field in editableFields" :key="field" class="modal-field">
            <span>{{ field }}</span>
            <input v-model="editForm[field]" />
          </label>
        </div>
        <dl v-else class="view-grid">
          <div v-for="field in viewFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ entry[field] ?? '—' }}</dd>
          </div>
        </dl>
        <div class="card-foot">
          <template v-if="canManage">
            <button class="btn primary" type="button" @click="saveFields">保存档案修改</button>
            <span class="cell-hint">修改将记入动态台账，不能清空字段。</span>
          </template>
          <span v-else-if="store.isReadOnly" class="readonly-tag">只读岗：无编辑授权</span>
          <span v-else class="readonly-tag">{{ denyHint }}</span>
        </div>
      </article>

      <!-- 状态动作 -->
      <article class="detail-card">
        <h3>维修 / 年检 / 报废</h3>
        <p class="cell-hint">当前状态：{{ entry['车辆状态'] }}（数据状态 {{ entry.status }}，两处同源）</p>
        <div class="action-row">
          <template v-if="canManage && entry.status !== '已报废'">
            <button
              v-for="action in availableActions"
              :key="action"
              class="btn"
              :class="{ danger: action === '申请报废' }"
              type="button"
              @click="runAction(action)"
            >
              {{ action }}
            </button>
          </template>
          <span v-else class="readonly-tag">
            {{ entry.status === '已报废' ? '车辆已报废，动作终止' : denyHint }}
          </span>
        </div>
      </article>

      <!-- 换人交接 -->
      <article class="detail-card">
        <h3>归属交接（换人留痕）</h3>
        <form v-if="canManage" class="handover-form" @submit.prevent="submitHandover">
          <label class="modal-field">
            <span>接任车辆管理员<em>*</em></span>
            <select v-model="successorId" required>
              <option value="" disabled>请选择接任人（须为车辆管理员）</option>
              <option v-for="person in adminCandidates" :key="person.id" :value="person.id">
                {{ person.班组 }} · {{ person.姓名 }} · {{ person.岗位 }}
              </option>
            </select>
          </label>
          <label class="modal-field">
            <span>交接备注</span>
            <input v-model="handoverRemark" placeholder="如：库区调整、人员轮岗" />
          </label>
          <div class="card-foot">
            <button class="btn primary" type="submit">确认交接</button>
            <span class="cell-hint">交接后车辆归属切到接任人班组，历史台账仍记原班组。</span>
          </div>
        </form>
        <p v-else class="readonly-tag">{{ denyHint }}</p>
      </article>

      <!-- 历任责任人 -->
      <article class="detail-card">
        <h3>历任责任人</h3>
        <ol class="timeline">
          <li v-for="(owner, index) in owners" :key="`${owner['工号']}-${index}`">
            <span class="timeline-time">{{ owner['自'] }}</span>
            <span class="team-tag">{{ owner['班组'] }}</span>
            <strong>{{ owner['姓名'] }}</strong>
            <span class="cell-hint">工号 {{ owner['工号'] }}</span>
            <em v-if="index === owners.length - 1 && owner['工号'] === entry['责任人工号']" class="current-flag">现任</em>
          </li>
        </ol>
      </article>

      <!-- 动态台账：历史条目的班组/操作人是快照，归属调整后不被顶掉 -->
      <article class="detail-card">
        <h3>动态台账（登记、维修、年检、报废、档案修改、交接）</h3>
        <table class="data-table ledger-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>动作</th>
              <th>发生时归属班组</th>
              <th>操作人</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in ledger" :key="index">
              <td>{{ item['时间'] }}</td>
              <td>{{ item['动作'] }}</td>
              <td><span class="team-tag">{{ item['班组'] }}</span></td>
              <td>{{ item['操作人'] }}（{{ item['操作人工号'] }}）</td>
              <td>{{ item['说明'] }}</td>
            </tr>
          </tbody>
        </table>
      </article>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

interface LedgerItem {
  时间: string
  动作: string
  班组: string
  操作人工号: string
  操作人: string
  说明: string
}
interface OwnerItem {
  工号: string
  姓名: string
  班组: string
  自: string
}
type Entry = Record<string, string | number | LedgerItem[] | OwnerItem[]>

const route = useRoute()
const store = useSessionStore()

const editableFields = ['核定载重', '年检日期', '行驶区域', '驾驶员']
const viewFields = ['车辆编号', '车辆类型', '动力类型', '核定载重', '行驶区域', '驾驶员', '年检日期', '车辆状态']
const allActions = ['安排维修', '安排年检', '申请报废']

const entry = ref<Entry | null>(null)
const notFound = ref(false)
const banner = ref('')
const bannerOk = ref(false)
const editForm = reactive<Record<string, string>>({})
const successorId = ref('')
const handoverRemark = ref('')

const entryId = computed(() => Number(route.params.id))
const canManage = computed(() => !!entry.value && store.canManage(String(entry.value['归属班组'])))
const ledger = computed<LedgerItem[]>(() => (entry.value?.['动态台账'] as LedgerItem[]) ?? [])
const owners = computed<OwnerItem[]>(() => (entry.value?.['历任责任人'] as OwnerItem[]) ?? [])
const denyHint = computed(() => {
  if (!entry.value) return ''
  if (store.isReadOnly) return '只读岗：仅可查看，维修、年检、报废与交接均无授权'
  if (store.isAdmin) {
    return `本车归属${entry.value['归属班组']}，代办需持有该班组车辆管理员授权，当前无权操作`
  }
  return '仅归属班组的车辆管理员可办理，当前岗位无授权'
})
const adminCandidates = computed(() => store.staff.filter((person) => person.岗位 === '车辆管理员'))
const availableActions = computed(() => {
  if (!entry.value) return []
  const status = String(entry.value.status)
  return allActions.filter((action) => {
    if (action === '安排维修') return status !== '维修中'
    if (action === '安排年检') return status !== '待年检'
    return true
  })
})

async function reload() {
  notFound.value = false
  try {
    const response = await request(`/api/forklift/${entryId.value}`)
    if (response.status === 404) {
      notFound.value = true
      return
    }
    if (!response.ok) throw new Error('车辆详情读取失败')
    entry.value = await response.json()
    for (const field of editableFields) {
      editForm[field] = String(entry.value?.[field] ?? '')
    }
  } catch (error) {
    bannerOk.value = false
    banner.value = error instanceof Error ? error.message : '车辆详情读取失败'
  }
}

function flash(ok: boolean, message: string) {
  bannerOk.value = ok
  banner.value = message
}

async function saveFields() {
  banner.value = ''
  try {
    const response = await request(`/api/forklift/${entryId.value}`, {
      method: 'PATCH',
      body: JSON.stringify({ values: { ...editForm } }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    flash(!!payload.ok, payload.message || '保存失败')
    await reload()
  } catch (error) {
    flash(false, error instanceof Error ? error.message : '保存失败')
  }
}

async function runAction(action: string) {
  banner.value = ''
  try {
    const response = await request(`/api/forklift/${entryId.value}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    flash(!!payload.ok, payload.message)
    await reload()
  } catch (error) {
    flash(false, error instanceof Error ? error.message : '操作失败')
  }
}

async function submitHandover() {
  banner.value = ''
  try {
    const response = await request(`/api/forklift/${entryId.value}/handover`, {
      method: 'POST',
      body: JSON.stringify({
        values: { successor_id: successorId.value },
        remark: handoverRemark.value || null,
      }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    flash(!!payload.ok, payload.message)
    if (payload.ok) {
      successorId.value = ''
      handoverRemark.value = ''
    }
    await reload()
  } catch (error) {
    flash(false, error instanceof Error ? error.message : '交接失败')
  }
}

onMounted(reload)
</script>

<style scoped>
.detail-page {
  display: block;
}
.detail-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 14px;
}
.detail-card h3 {
  margin: 0 0 10px;
  font-size: 15px;
}
.banner {
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
  font-size: 13px;
}
.banner.ok {
  background: #ecfdf3;
  border: 1px solid #a6f4c5;
  color: #027a48;
}
.banner.deny {
  background: #fef3f2;
  border: 1px solid #fda29b;
  color: #b42318;
}
.edit-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 16px;
}
.view-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 24px;
  margin: 0;
}
.view-grid dt {
  font-size: 12px;
  color: var(--muted);
}
.view-grid dd {
  margin: 0 0 4px;
  font-size: 13px;
}
.modal-field {
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
.card-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}
.action-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.btn.danger {
  border-color: #d92d20;
  color: #d92d20;
}
.readonly-tag {
  color: var(--muted);
  font-size: 12px;
}
.handover-form {
  max-width: 520px;
}
.cell-hint {
  color: var(--muted);
  font-size: 12px;
}
.team-tag {
  background: #eff8ff;
  border: 1px solid #b2ddff;
  color: #175cd3;
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 12px;
}
.timeline {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
}
.timeline-time {
  color: var(--muted);
  font-size: 12px;
  margin-right: 8px;
}
.current-flag {
  margin-left: 8px;
  background: #ecfdf3;
  color: #027a48;
  border-radius: 999px;
  padding: 0 8px;
  font-size: 11px;
  font-style: normal;
}
.ledger-table th,
.ledger-table td {
  font-size: 12px;
}
</style>
