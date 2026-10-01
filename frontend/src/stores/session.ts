import { defineStore } from 'pinia'

import { request } from '@/api/client'

export interface Staff {
  id: string
  姓名: string
  班组: string
  岗位: string
}

const STORAGE_KEY = 'forklift.operatorId'
const ROLE_ADMIN = '车辆管理员'
const ROLE_READONLY = '只读岗'

export const useSessionStore = defineStore('session', {
  state: () => ({
    staff: [] as Staff[],
    operatorId: localStorage.getItem(STORAGE_KEY) || '',
    current: null as Staff | null,
  }),
  getters: {
    isReadOnly: (state) => state.current?.岗位 === ROLE_READONLY,
    isAdmin: (state) => state.current?.岗位 === ROLE_ADMIN,
    canOperate: (state) => !!state.current && state.current.岗位 !== ROLE_READONLY,
  },
  actions: {
    async bootstrap() {
      try {
        const response = await request('/api/session/staff')
        if (response.ok) {
          const payload = (await response.json()) as { items: Staff[] }
          this.staff = payload.items ?? []
        }
      } catch {
        // 名册加载失败不阻断页面，列表仍可读
      }
      await this.switchTo(this.operatorId || undefined)
    },
    async switchTo(id?: string) {
      this.operatorId = id || ''
      localStorage.setItem(STORAGE_KEY, this.operatorId)
      try {
        const response = await request('/api/session/me')
        this.current = response.ok ? ((await response.json()) as Staff) : null
      } catch {
        this.current = null
      }
    },
    /** 是否是某班组的归属车辆管理员；列表与详情页的操作入口都按这个口径收口。 */
    canManage(team: string): boolean {
      return !!this.current && this.current.岗位 === ROLE_ADMIN && this.current.班组 === team
    },
  },
})
