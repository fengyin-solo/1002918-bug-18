import { defineStore } from 'pinia'

export interface SessionUser {
  id: string
  name: string
  role: string
  team: string
  title: string
}

const STORAGE_KEY = 'forklift.operatorId'
const DEFAULT_OPERATOR_ID = 'u5' // 默认只读岗，遵循最小权限

export const useSessionStore = defineStore('session', {
  state: () => ({
    operatorId: localStorage.getItem(STORAGE_KEY) || DEFAULT_OPERATOR_ID,
    users: [] as SessionUser[],
    shiftLabel: '白班 08:00-20:00',
    scope: '特种设备安全管理平台',
  }),
  getters: {
    currentUser(state): SessionUser | undefined {
      return state.users.find((user) => user.id === state.operatorId)
    },
    operator(): string {
      return this.currentUser?.name ?? '未识别身份'
    },
    role(): string {
      return this.currentUser?.role ?? '—'
    },
    team(): string {
      return this.currentUser?.team ?? '—'
    },
    isAdmin(): boolean {
      return this.currentUser?.role === '车辆管理员'
    },
  },
  actions: {
    setUsers(users: SessionUser[]) {
      this.users = users
      if (!users.some((user) => user.id === this.operatorId)) {
        this.operatorId = DEFAULT_OPERATOR_ID
      }
    },
    switchUser(id: string) {
      this.operatorId = id
      localStorage.setItem(STORAGE_KEY, id)
    },
  },
})
