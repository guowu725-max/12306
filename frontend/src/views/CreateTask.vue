<template>
  <div class="create-task-page">
    <el-card>
      <template #header>
        <span>{{ isEditMode ? '编辑抢票任务' : '创建抢票任务' }}</span>
      </template>

      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px" class="task-form">
        <el-divider content-position="left">基本信息</el-divider>

        <el-form-item label="任务名称" prop="name">
          <el-input v-model="form.name" placeholder="如：工作日早班车" />
        </el-form-item>

        <el-row :gutter="16">
          <el-col :xs="24" :sm="12">
            <el-form-item label="出发站" prop="from_station">
              <el-select
                v-model="form.from_station"
                filterable
                remote
                :remote-method="searchFromStation"
                :loading="loadingFrom"
                placeholder="输入站名搜索"
                style="width: 100%"
              >
                <el-option v-for="item in fromStations" :key="item.code" :label="item.name" :value="item.name" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="到达站" prop="to_station">
              <el-select
                v-model="form.to_station"
                filterable
                remote
                :remote-method="searchToStation"
                :loading="loadingTo"
                placeholder="输入站名搜索"
                style="width: 100%"
              >
                <el-option v-for="item in toStations" :key="item.code" :label="item.name" :value="item.name" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">执行计划</el-divider>

        <el-form-item label="任务模式">
          <el-radio-group v-model="form.schedule_mode">
            <el-radio value="once">一次性任务</el-radio>
            <el-radio value="daily">每天自动监控</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-row v-if="form.schedule_mode === 'daily'" :gutter="16">
          <el-col :xs="24" :sm="12">
            <el-form-item label="每日启动" prop="daily_start_time">
              <el-time-select
                v-model="form.daily_start_time"
                start="00:00"
                step="00:05"
                end="23:55"
                placeholder="每天几点开始"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="企微确认">
              <el-switch v-model="form.confirmation_required" disabled />
              <span class="form-tip inline-tip">每日任务固定为“发现余票后先微信确认，再提交订单”</span>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="日期策略">
          <el-radio-group v-model="form.date_strategy">
            <el-radio value="fixed">固定乘车日期</el-radio>
            <el-radio value="offset">每天动态计算</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-row :gutter="16">
          <el-col v-if="form.date_strategy === 'fixed'" :xs="24" :sm="12">
            <el-form-item label="出发日期" prop="train_date">
              <el-date-picker
                v-model="form.train_date"
                type="date"
                value-format="YYYY-MM-DD"
                format="YYYY-MM-DD"
                :disabled-date="disabledDate"
                placeholder="选择日期"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col v-else :xs="24" :sm="12">
            <el-form-item label="日期偏移">
              <el-input-number v-model="form.date_offset_days" :min="0" :max="15" />
              <span class="unit-text">天后</span>
              <div class="form-tip">例如 14 表示每天运行时监控“今天 + 14 天”的车票。</div>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="出发时间段">
              <div class="time-range">
                <el-time-select v-model="form.start_time_min" start="00:00" step="00:30" end="23:30" placeholder="最早" />
                <span>至</span>
                <el-time-select v-model="form.start_time_max" start="00:00" step="00:30" end="23:30" placeholder="最晚" />
              </div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">筛选条件</el-divider>

        <el-form-item label="车次类型">
          <el-checkbox-group v-model="form.train_types">
            <el-checkbox v-for="item in trainTypeOptions" :key="item.value" :value="item.value">
              {{ item.label }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-form-item label="席别优先级" prop="seat_types">
          <el-checkbox-group v-model="form.seat_types">
            <el-checkbox v-for="(label, code) in seatTypeMap" :key="code" :value="code">{{ label }}</el-checkbox>
          </el-checkbox-group>
          <div class="form-tip">勾选顺序即尝试顺序；建议只选择你真正接受的席别。</div>
        </el-form-item>

        <el-form-item label="指定车次">
          <div class="row-control">
            <el-select
              v-model="form.train_codes"
              multiple
              filterable
              allow-create
              placeholder="如 G101、G103；留空表示不限"
              style="flex: 1"
            >
              <el-option v-for="code in availableTrainCodes" :key="code" :label="code" :value="code" />
            </el-select>
            <el-button :loading="loadingTrains" @click="queryTrainCodes">查询车次</el-button>
          </div>
        </el-form-item>

        <el-divider content-position="left">乘车人</el-divider>

        <el-form-item label="乘车人" prop="passengers">
          <el-table :data="form.passengers" border style="width: 100%">
            <el-table-column prop="passenger_name" label="姓名" min-width="90" />
            <el-table-column prop="passenger_id_no" label="证件号" min-width="180" show-overflow-tooltip />
            <el-table-column label="票种" width="120">
              <template #default="{ row }">
                <el-select v-model="row.passenger_type" size="small">
                  <el-option label="成人票" value="1" />
                  <el-option label="儿童票" value="2" />
                  <el-option label="学生票" value="3" />
                  <el-option label="残军票" value="4" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ $index }">
                <el-button type="danger" link @click="form.passengers.splice($index, 1)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-button class="add-btn" @click="openPassengerDialog">添加 12306 联系人</el-button>
        </el-form-item>

        <el-divider content-position="left">运行参数</el-divider>

        <el-row :gutter="16">
          <el-col :xs="24" :sm="8">
            <el-form-item label="查询间隔">
              <el-input-number v-model="form.query_interval" :min="3" :max="60" />
              <span class="unit-text">秒</span>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="最大查询">
              <el-input-number v-if="!isInfiniteRetry" v-model="form.max_retry_count" :min="1" :max="100000" />
              <span v-else class="unit-text">无限</span>
              <el-checkbox v-model="isInfiniteRetry" @change="handleInfiniteChange">无限</el-checkbox>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="自动提交">
              <el-switch v-model="form.auto_submit" :disabled="form.schedule_mode === 'daily'" />
              <span v-if="form.schedule_mode === 'daily'" class="form-tip inline-tip">每日任务仅在微信确认后提交</span>
            </el-form-item>
          </el-col>
        </el-row>

        <el-alert
          v-if="form.schedule_mode === 'daily'"
          type="info"
          :closable="false"
          show-icon
          title="流程：每天定时监控 → 发现余票 → 企业微信卡片确认 → 重新查余票 → 提交订单 → 去官方 12306 支付。"
        />

        <el-form-item class="submit-row">
          <el-button type="primary" :loading="submitting" @click="handleSubmit">
            {{ isEditMode ? '保存修改' : '创建任务' }}
          </el-button>
          <el-button @click="router.back()">取消</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-dialog v-model="passengerDialogVisible" title="选择 12306 联系人" width="640px">
      <el-table :data="contactPassengers" v-loading="loadingPassengers" @selection-change="selectedContacts = $event" height="400">
        <el-table-column type="selection" width="55" />
        <el-table-column prop="passenger_name" label="姓名" min-width="90" />
        <el-table-column prop="passenger_id_no" label="证件号" min-width="180" show-overflow-tooltip />
        <el-table-column prop="mobile_no" label="手机号" min-width="120" />
      </el-table>
      <template #footer>
        <el-button @click="passengerDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAddPassengers">添加选中</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import { useTaskStore } from '../stores/task'
import { useUserStore } from '../stores/user'

const router = useRouter()
const route = useRoute()
const taskStore = useTaskStore()
const userStore = useUserStore()
const formRef = ref(null)
const submitting = ref(false)
const loadingFrom = ref(false)
const loadingTo = ref(false)
const loadingTrains = ref(false)
const loadingPassengers = ref(false)
const passengerDialogVisible = ref(false)
const fromStations = ref([])
const toStations = ref([])
const availableTrainCodes = ref([])
const contactPassengers = ref([])
const selectedContacts = ref([])
const isInfiniteRetry = ref(false)

const trainTypeOptions = [
  { value: 'G', label: '高铁 G' },
  { value: 'D', label: '动车 D' },
  { value: 'C', label: '城际 C' },
  { value: 'Z', label: '直达 Z' },
  { value: 'T', label: '特快 T' },
  { value: 'K', label: '快速 K' }
]

const seatTypeMap = {
  '9': '商务座',
  'M': '一等座',
  'O': '二等座',
  '4': '软卧',
  '3': '硬卧',
  '1': '硬座'
}

const form = reactive({
  name: '',
  from_station: '',
  to_station: '',
  train_date: '',
  train_types: ['G', 'D'],
  seat_types: ['O'],
  train_codes: [],
  start_time_min: '',
  start_time_max: '',
  passengers: [],
  query_interval: 5,
  max_retry_count: 100,
  auto_submit: true,
  schedule_mode: 'once',
  daily_start_time: '07:00',
  date_strategy: 'fixed',
  date_offset_days: 14,
  confirmation_required: false
})

const isEditMode = computed(() => !!route.params.id)

watch(() => form.schedule_mode, (mode) => {
  if (mode === 'daily') {
    form.confirmation_required = true
    form.auto_submit = false
  }
})

const rules = {
  name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  from_station: [{ required: true, message: '请选择出发站', trigger: 'change' }],
  to_station: [{ required: true, message: '请选择到达站', trigger: 'change' }],
  train_date: [{
    validator: (_rule, value, callback) => {
      if (form.date_strategy === 'fixed' && !value) callback(new Error('固定日期策略必须选择出发日期'))
      else callback()
    },
    trigger: 'change'
  }],
  daily_start_time: [{
    validator: (_rule, value, callback) => {
      if (form.schedule_mode === 'daily' && !value) callback(new Error('请选择每日启动时间'))
      else callback()
    },
    trigger: 'change'
  }],
  seat_types: [{ required: true, message: '请选择至少一个席别', trigger: 'change' }],
  passengers: [{
    validator: (_rule, value, callback) => {
      if (!value || value.length === 0) callback(new Error('请添加至少一个乘车人'))
      else callback()
    },
    trigger: 'change'
  }]
}

const disabledDate = (time) => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const max = new Date(today)
  max.setDate(max.getDate() + 15)
  return time.getTime() < today.getTime() || time.getTime() > max.getTime()
}

const dynamicQueryDate = () => {
  if (form.date_strategy === 'fixed') return form.train_date
  const date = new Date()
  date.setDate(date.getDate() + Number(form.date_offset_days || 0))
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const searchFromStation = async (query) => {
  if (!query) return
  loadingFrom.value = true
  try { fromStations.value = (await api.searchStations(query)).stations || [] } finally { loadingFrom.value = false }
}

const searchToStation = async (query) => {
  if (!query) return
  loadingTo.value = true
  try { toStations.value = (await api.searchStations(query)).stations || [] } finally { loadingTo.value = false }
}

const queryTrainCodes = async () => {
  const trainDate = dynamicQueryDate()
  if (!form.from_station || !form.to_station || !trainDate) {
    ElMessage.warning('请先填写出发站、到达站和日期策略')
    return
  }
  loadingTrains.value = true
  try {
    const params = {
      from_station: form.from_station,
      to_station: form.to_station,
      train_date: trainDate
    }
    if (form.start_time_min) params.start_time_min = form.start_time_min
    if (form.start_time_max) params.start_time_max = form.start_time_max
    if (form.train_types.length) params.train_types = form.train_types.join(',')
    const res = await api.queryTickets(params)
    availableTrainCodes.value = (res.data || []).map(item => item.train_code)
    ElMessage.success(`查询到 ${availableTrainCodes.value.length} 个车次`)
  } catch (error) {
    ElMessage.error(`查询车次失败: ${error.message}`)
  } finally {
    loadingTrains.value = false
  }
}

const openPassengerDialog = async () => {
  passengerDialogVisible.value = true
  if (contactPassengers.value.length) return
  loadingPassengers.value = true
  try {
    const res = await api.getPassengers()
    if (res.success) contactPassengers.value = res.data || []
    else ElMessage.warning(res.message || '获取联系人失败')
  } catch (error) {
    ElMessage.error(`获取联系人失败: ${error.message}`)
  } finally {
    loadingPassengers.value = false
  }
}

const confirmAddPassengers = () => {
  selectedContacts.value.forEach(contact => {
    if (!form.passengers.some(item => item.passenger_id_no === contact.passenger_id_no)) {
      form.passengers.push({ ...contact })
    }
  })
  passengerDialogVisible.value = false
}

const handleInfiniteChange = (value) => {
  form.max_retry_count = value ? -1 : 100
}

const handleSubmit = async () => {
  if (!userStore.currentUser || !userStore.isLoggedIn) {
    ElMessage.warning('请先登录 12306')
    return
  }
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    const taskData = {
      name: form.name,
      from_station: form.from_station,
      to_station: form.to_station,
      train_date: form.date_strategy === 'fixed' ? form.train_date : null,
      train_types: form.train_types,
      seat_types: form.seat_types,
      train_codes: form.train_codes,
      passengers: form.passengers,
      query_interval: form.query_interval,
      max_retry_count: form.max_retry_count,
      auto_submit: form.schedule_mode === 'daily' ? false : form.auto_submit,
      start_time_range: form.start_time_min && form.start_time_max ? `${form.start_time_min}-${form.start_time_max}` : null,
      schedule_mode: form.schedule_mode,
      daily_start_time: form.schedule_mode === 'daily' ? form.daily_start_time : null,
      date_strategy: form.date_strategy,
      date_offset_days: Number(form.date_offset_days || 0),
      confirmation_required: form.schedule_mode === 'daily' ? true : form.confirmation_required
    }

    if (isEditMode.value) {
      await taskStore.updateTask(route.params.id, taskData)
      ElMessage.success('任务更新成功')
    } else {
      await taskStore.createTask(taskData)
      ElMessage.success('任务创建成功')
    }
    router.push('/tasks')
  } catch (error) {
    ElMessage.error(error.message || '保存任务失败')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  if (!isEditMode.value) {
    if (route.query.from) {
      form.from_station = String(route.query.from)
      fromStations.value = [{ name: form.from_station, code: 'QUERY_FROM' }]
    }
    if (route.query.to) {
      form.to_station = String(route.query.to)
      toStations.value = [{ name: form.to_station, code: 'QUERY_TO' }]
    }
    if (route.query.date) form.train_date = String(route.query.date)
    if (route.query.codes) form.train_codes = String(route.query.codes).split(',').filter(Boolean)
    if (form.from_station && form.to_station) form.name = `${form.from_station}-${form.to_station} 抢票`
    return
  }

  try {
    const task = await taskStore.getTask(route.params.id)
    if (!task) return
    Object.assign(form, {
      name: task.name,
      from_station: task.from_station,
      to_station: task.to_station,
      train_date: task.train_date,
      train_types: task.train_types ? task.train_types.split(',') : [],
      seat_types: task.seat_types ? task.seat_types.split(',') : [],
      train_codes: task.train_codes ? task.train_codes.split(',') : [],
      passengers: task.passengers ? JSON.parse(task.passengers) : [],
      query_interval: task.query_interval,
      max_retry_count: task.max_retry_count,
      auto_submit: task.auto_submit,
      schedule_mode: task.schedule_mode || 'once',
      daily_start_time: task.daily_start_time || '07:00',
      date_strategy: task.date_strategy || 'fixed',
      date_offset_days: Math.min(task.date_offset_days ?? 14, 15),
      confirmation_required: !!task.confirmation_required
    })
    if (task.start_time_range) {
      const [start, end] = task.start_time_range.split('-')
      form.start_time_min = start
      form.start_time_max = end
    }
    isInfiniteRetry.value = task.max_retry_count === -1
    fromStations.value = [{ name: task.from_station, code: 'EDIT_FROM' }]
    toStations.value = [{ name: task.to_station, code: 'EDIT_TO' }]
  } catch (error) {
    ElMessage.error(`加载任务失败: ${error.message || ''}`)
  }
})
</script>

<style scoped>
.task-form { max-width: 980px; }
.time-range, .row-control { display: flex; align-items: center; gap: 8px; width: 100%; }
.time-range .el-select { flex: 1; }
.form-tip { color: #909399; font-size: 12px; margin-top: 4px; width: 100%; }
.inline-tip { margin-left: 10px; width: auto; }
.unit-text { margin: 0 8px; color: #606266; }
.add-btn { width: 100%; margin-top: 12px; border-style: dashed; }
.submit-row { margin-top: 24px; }
@media (max-width: 768px) {
  .task-form { max-width: 100%; }
  .time-range { align-items: flex-start; }
}
</style>
