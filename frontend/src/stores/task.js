import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

export const useTaskStore = defineStore('task', () => {
  const tasks = ref([])
  const currentTask = ref(null)
  const taskLogs = ref([])
  const loading = ref(false)

  async function fetchTasks(status = null) {
    loading.value = true
    try {
      const res = await api.getTasks({ status })
      tasks.value = res.tasks || []
    } catch (error) {
      console.error('获取任务列表失败:', error)
    } finally {
      loading.value = false
    }
  }

  async function getTask(taskId) {
    try {
      const res = await api.getTask(taskId)
      if (res.success) {
        currentTask.value = res.data
        return res.data
      }
    } catch (error) {
      console.error('获取任务详情失败:', error)
    }
  }

  async function createTask(taskData) {
    const res = await api.createTask(taskData)
    if (res.success) {
      tasks.value.unshift(res.data)
      return res.data
    }
  }

  async function updateTask(taskId, taskData) {
    const res = await api.updateTask(taskId, taskData)
    if (res.success) {
      const numericId = Number(taskId)
      const index = tasks.value.findIndex(t => Number(t.id) === numericId)
      if (index !== -1) tasks.value[index] = res.data
      currentTask.value = res.data
      return res.data
    }
  }

  async function startTask(taskId) {
    const res = await api.startTask(taskId)
    if (res.success) {
      const task = tasks.value.find(t => Number(t.id) === Number(taskId))
      if (task) task.status = task.schedule_mode === 'daily' ? 'pending' : 'running'
    }
    return res
  }

  async function stopTask(taskId) {
    const res = await api.stopTask(taskId)
    if (res.success) {
      const task = tasks.value.find(t => Number(t.id) === Number(taskId))
      if (task) task.status = 'paused'
    }
    return res
  }

  async function cancelTask(taskId) {
    const res = await api.cancelTask(taskId)
    if (res.success) {
      const task = tasks.value.find(t => Number(t.id) === Number(taskId))
      if (task) task.status = 'cancelled'
    }
    return res
  }

  async function deleteTask(taskId) {
    const res = await api.deleteTask(taskId)
    if (res.success) tasks.value = tasks.value.filter(t => Number(t.id) !== Number(taskId))
    return res
  }

  async function fetchTaskLogs(taskId) {
    try {
      const res = await api.getTaskLogs(taskId)
      taskLogs.value = res.logs || []
    } catch (error) {
      console.error('获取任务日志失败:', error)
    }
  }

  return {
    tasks,
    currentTask,
    taskLogs,
    loading,
    fetchTasks,
    getTask,
    createTask,
    updateTask,
    startTask,
    stopTask,
    cancelTask,
    deleteTask,
    fetchTaskLogs
  }
})
