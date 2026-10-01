<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">特种设备安全管理平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向锅炉、压力容器、电梯、起重机械与场内专用机动车辆等特种设备的注册登记、定期检验、维保监管与隐患排查的一体化安全管理后台。</span>
        <span class="head-user">
          <label class="identity-picker">
            当前身份
            <select :value="store.operatorId" @change="onSwitch(($event.target as HTMLSelectElement).value)">
              <option value="">默认（演示）</option>
              <option v-for="person in store.staff" :key="person.id" :value="person.id">
                {{ person.班组 }} · {{ person.姓名 }} · {{ person.岗位 }}
              </option>
            </select>
          </label>
          <em v-if="store.current" class="identity-badge" :class="{ readonly: store.isReadOnly }">
            {{ store.current.班组 }} {{ store.current.姓名 }}（{{ store.current.岗位 }}）
          </em>
        </span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'

import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const navItems = [{ label: "运营概览", path: "/" }, { label: "使用登记", path: "/register" }, { label: "锅炉管理", path: "/boiler" }, { label: "压力容器", path: "/pressurevessel" }, { label: "压力管道", path: "/pipeline" }, { label: "电梯管理", path: "/elevator" }, { label: "起重机械", path: "/crane" }, { label: "场车管理", path: "/forklift" }, { label: "定期检验", path: "/inspection" }, { label: "维保记录", path: "/maintenance" }, { label: "隐患排查", path: "/hazard" }, { label: "事故管理", path: "/accident" }, { label: "作业人员", path: "/operator" }, { label: "培训考核", path: "/training" }, { label: "安全阀校验", path: "/safetyvalve" }, { label: "压力表检定", path: "/gauge" }, { label: "备件管理", path: "/sparepart" }, { label: "应急演练", path: "/emergency" }, { label: "能效监测", path: "/energyeff" }, { label: "档案管理", path: "/archive" }, { label: "维保合同", path: "/contract" }]

async function onSwitch(id: string) {
  await store.switchTo(id || undefined)
}

onMounted(() => {
  void store.bootstrap()
})
</script>

<style scoped>
.identity-picker {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-style: normal;
}
.identity-picker select {
  padding: 3px 6px;
  border-radius: 6px;
  border: 1px solid var(--border);
  font-size: 12px;
}
.identity-badge {
  padding: 2px 8px;
  border-radius: 999px;
  background: #ecfdf3;
  color: #027a48;
  font-style: normal;
  font-size: 12px;
}
.identity-badge.readonly {
  background: #f2f4f7;
  color: #475467;
}
</style>
