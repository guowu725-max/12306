<template>
  <div v-if="task" class="task-detail-page">
    <el-page-header @back="router.back()">
      <template #content>
        <span class="title">{{ task.name }}</span>
        <el-tag :type="statusType">{{ statusText }}</el-tag>
      </template>
      <template #extra>
        <el-button-group>
          <template v-if="isDaily">
            <el-button v-if="task.status === 'paused'" type="success" @click="handleStart">启用每日计划</el-button>
            <el-button v-if="['pending', 'running'].includes(task.status)" type="warning" @click="handleStop">暂停每日计划</el-button>
            <el-button v-if="task.status !== 'cancelled'" type="danger" @click="handleCancel">取消任务</el-button>
          </template>
          <template v-else>
            <el-button v-if="['pending', 'paused'].includes(task.status)" type="success" @click="handleStart">启动任务</el-button>
            <el-button v-if="task.status === 'running'" type="warning" @click="handleStop">暂停任务</el-button>
            <el-button v-if="task.status === 'running'" type="danger" @click="handleCancel">取消任务</el-button>
          </template>
        </el-button-group>
      </template>
    </el-page-header>

    <el-row :gutter="20" class="content-row">
      <el-col :xs="24" :md="12">
        <el-card>
          <template #header>任务信息</template>
          <el-descriptions :column="isMobile ? 1 : 2" border>
            <el-descriptions-item label="行程">{{ task.from_station }} → {{ task.to_station }}</el-descriptions-item>
            <el-descriptions-item label="任务模式">
              <el-tag :type="isDaily ? 'success' : 'info'">{{ isDaily ? '每天自动监控' : '一次性任务' }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item v-if="isDaily" label="每日启动">{{ task.daily_start_time }}</el-descriptions-item>
            <el-descriptions-item label="乘车日期">{{ dateDescription }}</el-descriptions-item>
            <el-descriptions-item label="车次类型">{{ task.train_types || '不限' }}</el-descriptions-item>
            <el-descriptions-item label="指定车次">{{ task.train_codes || '不限' }}</el-descriptions-item>
            <el-descriptions-item label="席别">{{ formatSeatTypes(task.seat_types) }}</el-descriptions-item>
            <el-descriptions-item label="时间段">{{ task.start_time_range || '全天' }}</el-descriptions-item>
            <el-descriptions-item label="查询间隔">{{ task.query_interval }} 秒</el-descriptions-item>
            <el-descriptions-item label="最大查询">{{ task.max_retry_count === -1 ? '无限' : task.max_retry_count }}</el-descriptions-item>
            <el-descriptions-item label="下单方式" :span="isMobile ? 1 : 2">
              <el-tag v-if="isDaily && task.confirmation_required" type="warning">企业微信确认后提交</el-tag>
              <el-tag v-else :type="task.auto_submit ? 'success' : 'info'">{{ task.auto_submit ? '自动提交' : '仅监控' }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item v-if="isDaily" label="今日运行">{{ task.last_daily_run_date || '-' }}</el-descriptions-item>
            <el-descriptions-item v-if="isDaily" label="最近成功">{{ task.last_daily_success_date || '-' }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatTime(task.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="开始时间">{{ formatTime(task.started_at) }}</el-descriptions-item>
          </el-descriptions>

          <div class="section-title">乘车人</div>
          <el-table :data="passengers" stripe border size="small">
            <el-table-column prop="passenger_name" label="姓名" min-width="80" />
            <el-table-column prop="passenger_id_no" label="证件号" min-width="150">
              <template #default="{ row }">{{ maskIdNo(row.passenger_id_no) }}</template>
            </el-table-column>
            <el-table-column prop="mobile_no" label="手机号" min-width="110" />
          </el-table>

          <el-alert
            v-if="isDaily"
            class="flow-alert"
            type="info"
            :closable="false"
            title="发现余票后会发送企业微信卡片；只有点击确认并重新查到余票后才会提交订单。"
          />

          <div v-if="task.order_id" class="order-box">
            <div>
              <strong>最近订单：{{ task.order_id }}</strong>
              <div class="muted">{{ task.result_message || '订单已提交，请尽快支付' }}</div>
            </div>
            <el-button type="primary" @click="goToPayment">去官方 12306 支付</el-button>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="12" :class="{ mobileTop: isMobile }">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>运行日志</span>
              <el-button text type="primary" @click="refreshAll">刷新</el-button>
            </div>
          </template>
          <div class="log-container">
            <el-timeline>
              <el-timeline-item
                v-for="log in taskStore.taskLogs"
                :key="log.id"
                :type="getLogType(log.level)"
                :timestamp="formatTime(log.created_at)"
                placement="top"
              >
                <div class="log-message">{{ log.message }}</div>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-if="taskStore.taskLogs.length === 0" description="暂无日志" />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
  <el-empty v-else description="任务不存在" />
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTaskStore } from '../stores/task'

const route = useRoute()
const router = useRouter()
const taskStore = useTaskStore()
const isMobile = ref(window.innerWidth < 768)
const task = computed(() => taskStore.currentTask)
const isDaily = computed(() => task.value?.schedule_mode === 'daily')
let refreshTimer = null

const passengers = computed(() => {
  if (!task.value?.passengers) return []
  try { return JSON.parse(task.value.passengers) } catch { return [] }
})

const statusText = computed(() => {
  if (isDaily.value) {
    if (task.value.status === 'paused') return '每日计划已暂停'
    if (task.value.status === 'running') return '今日监控中'
    if (task.value.status === 'cancelled') return '已取消'
    return '每日计划已启用'
  }
  const map = { pending: '待运行', running: '运行中', paused: '已暂停', success: '成功', failed: '失败', cancelled: '已取消' }
  return map[task.value.status] || task.value.status
})

const statusType = computed(() => {
  const map = { pending: 'info', running: 'warning', paused: '', success: 'success', failed: 'danger', cancelled: 'info' }
  return map[task.value?.status] || 'info'
})

const dateDescription = computed(() => {
  if (!task.value) return '-'
  if (task.value.date_strategy === 'offset') return `每天运行时：当天 + ${task.value.date_offset_days} 天`
  return task.value.train_date
})

const formatSeatTypes = (types) => {
  const map = { O: '二等座', M: '一等座', 9: '商务座', 4: '软卧', 3: '硬卧', 1: '硬座' }
  return (types || '').split(',').filter(Boolean).map(item => map[item] || item).join('、')
}

const formatTime = (value) => value ? new Date(value).toLocaleString('zh-CN') : '-'
const maskIdNo = (value) => !value || value.length < 8 ? value : `${value.slice(0, 4)}****${value.slice(-4)}`
const getLogType = (level) => ({ info: 'primary', success: 'success', warning: 'warning', error: 'danger' }[level] || 'primary')

const refreshAll = async () => {
  const id = Number(route.params.id)
  await Promise.all([taskStore.getTask(id), taskStore.fetchTaskLogs(id)])
}

const handleStart = async () => {
  try {
    await taskStore.startTask(task.value.id)
    ElMessage.success(isDaily.value ? '每日计划已启用' : '任务已启动')
    await refreshAll()
  } catch (error) { ElMessage.error(error.message) }
}

const handleStop = async () => {
  try {
    await taskStore.stopTask(task.value.id)
    ElMessage.success(isDaily.value ? '每日计划已暂停' : '任务已暂停')
    await refreshAll()
  } catch (error) { ElMessage.error(error.message) }
}

const handleCancel = async () => {
  try {
    await ElMessageBox.confirm('确定取消该任务吗？', '确认', { type: 'warning' })
    await taskStore.cancelTask(task.value.id)
    ElMessage.success('任务已取消')
    await refreshAll()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '取消失败')
  }
}

const goToPayment = () => window.open('https://kyfw.12306.cn/otn/view/train_order.html', '_blank')
const handleResize = () => { isMobile.value = window.innerWidth < 768 }

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  await refreshAll()
  refreshTimer = setInterval(refreshAll, 5000)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
.title { font-size: 18px; font-weight: 600; margin-right: 10px; }
.content-row { margin-top: 20px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.section-title { margin: 22px 0 10px; font-weight: 600; }
.flow-alert { margin-top: 18px; }
.order-box { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-top: 18px; padding: 14px; border: 1px solid #b3e19d; background: #f0f9eb; border-radius: 6px; }
.muted { margin-top: 4px; color: #606266; font-size: 13px; }
.log-container { max-height: 680px; overflow: auto; }
.log-message { white-space: pre-wrap; word-break: break-word; line-height: 1.5; }
.mobileTop { margin-top: 16px; }
@media (max-width: 768px) { .order-box { align-items: flex-start; flex-direction: column; } }
</style>
