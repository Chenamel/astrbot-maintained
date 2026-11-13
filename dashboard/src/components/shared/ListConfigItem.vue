<template>
  <div class="d-flex align-center justify-space-between ga-2">
    <div v-if="isSingleItemMode" class="flex-grow-1 d-flex align-center ga-2">
      <v-text-field
        v-model="singleItemValue"
        :type="secretInputType"
        :append-inner-icon="secretToggleIcon"
        :autocomplete="secret ? 'new-password' : undefined"
        @click:append-inner="secretVisible = !secretVisible"
        hide-details
        variant="outlined"
        density="compact"
        class="flex-grow-1"
      ></v-text-field>
    </div>
    <div v-else>
      <span v-if="!modelValue || modelValue.length === 0" style="color: rgb(var(--v-theme-primaryText));">
        {{ t('core.common.list.noItems') }}
      </span>
      <div v-else class="d-flex flex-wrap ga-2">
        <v-chip v-for="item in displayItems" :key="item" size="x-small" label color="primary">
          {{ secret && !secretVisible ? '••••••••' : (item.length > 20 ? item.slice(0, 20) + '...' : item) }}
        </v-chip>
        <v-chip v-if="modelValue.length > maxDisplayItems" size="x-small" label color="grey-lighten-1">
          +{{ modelValue.length - maxDisplayItems }}
        </v-chip>
      </div>
    </div>
    <v-btn size="small" color="primary" variant="tonal" @click="openDialog">
      {{ preferSingleItem ? t('core.common.list.addMore') : (buttonText || t('core.common.list.modifyButton')) }}
    </v-btn>
  </div>

  <!-- List Management Dialog -->
  <v-dialog v-model="dialog" max-width="600px">
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">
        {{ dialogTitle || t('core.common.list.editTitle') }}
      </v-card-title>
      
      <!-- Add new item section - moved to top -->
      <v-card-text class="pa-4 pb-2">
        <div class="d-flex align-center ga-2">
          <v-text-field 
            v-model="newItem" 
            :type="secretInputType"
            :append-inner-icon="secretToggleIcon"
            :autocomplete="secret ? 'new-password' : undefined"
            @click:append-inner="secretVisible = !secretVisible"
            :label="t('core.common.list.addItemPlaceholder')" 
            @keyup.enter="addItem" 
            clearable 
            hide-details
            variant="outlined" 
            density="compact" 
            :placeholder="t('core.common.list.inputPlaceholder')"
            class="flex-grow-1">
          </v-text-field>
          <v-btn
            @click="addItem"
            variant="tonal"
            color="primary"
            size="small"
            :disabled="!newItem.trim()">
            {{ t('core.common.list.addButton') }}
          </v-btn>
          <v-btn 
            @click="showBatchImport = true" 
            variant="tonal" 
            color="primary"
            size="small">
            <v-icon size="small">mdi-import</v-icon>
            {{ t('core.common.list.batchImport') }}
          </v-btn>
          <v-btn
            v-if="picker === 'tools'"
            @click="openPicker"
            variant="tonal"
            color="primary"
            size="small">
            <v-icon size="small">mdi-format-list-checks</v-icon>
            {{ t('core.common.list.pickTools') }}
          </v-btn>
        </div>
      </v-card-text>

      <v-card-text class="pa-0" style="max-height: 400px; overflow-y: auto;">
        <v-list v-if="localItems.length > 0" density="compact">
          <v-list-item
            v-for="(item, index) in localItems"
            :key="index"
            rounded="md"
            class="ma-1 list-item-clickable"
            @click="startEdit(index, item)">
            <v-list-item-title v-if="editIndex !== index" class="item-text">
              {{ secret && !secretVisible ? '••••••••' : item }}
            </v-list-item-title>
            <v-text-field 
              v-else
              v-model="editItem" 
              :type="secretInputType"
              :append-inner-icon="secretToggleIcon"
              :autocomplete="secret ? 'new-password' : undefined"
              @click:append-inner="secretVisible = !secretVisible"
              hide-details 
              variant="outlined" 
              density="compact"
              @keyup.enter="saveEdit" 
              @keyup.esc="cancelEdit"
              @click.stop
              autofocus
            ></v-text-field>
            
            <template v-slot:append>
              <div class="d-flex">
                <v-btn
                  v-if="editIndex === index"
                  @click.stop="saveEdit" 
                  variant="text"
                  color="success" 
                  icon 
                  size="small">
                  <v-icon>mdi-check</v-icon>
                </v-btn>
                <v-btn
                  @click.stop="editIndex === index ? cancelEdit() : removeItem(index)" 
                  variant="text"
                  :color="editIndex === index ? 'error' : 'default'"
                  icon 
                  size="small">
                  <v-icon>mdi-close</v-icon>
                </v-btn>
              </div>
            </template>
          </v-list-item>
        </v-list>
        
        <div v-else class="text-center py-8">
          <v-icon size="64" color="grey-lighten-1">mdi-format-list-bulleted</v-icon>
          <p class="text-grey mt-4">{{ t('core.common.list.noItemsHint') }}</p>
        </div>
      </v-card-text>

      <v-card-actions class="pa-4">
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="cancelDialog">{{ t('core.common.cancel') }}</v-btn>
        <v-btn color="primary" variant="tonal" @click="confirmDialog">{{ t('core.common.confirm') }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Tool picker. A list of tool names is unreadable as free text: the names
       are internal identifiers, and nobody remembers which plugin registered
       which one. This asks the dashboard what tools exist and lets the reader
       tick them; typing stays available for names that are not live yet. -->
  <v-dialog v-model="showPicker" max-width="640px">
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">
        {{ t('core.common.list.pickToolsTitle') }}
      </v-card-title>
      <v-card-text class="pa-4 pb-1">
        <v-text-field
          v-model="pickerSearch"
          :label="t('core.common.list.pickToolsSearch')"
          prepend-inner-icon="mdi-magnify"
          variant="outlined"
          density="compact"
          hide-details
          clearable
        ></v-text-field>
        <p class="text-caption mt-2 mb-0" style="opacity: .7">
          {{ t('core.common.list.pickToolsHint') }}
        </p>
        <p v-if="pickerError" class="text-caption mt-1 mb-0 text-error">{{ pickerError }}</p>
      </v-card-text>

      <v-card-text class="pa-0" style="max-height: 420px; overflow-y: auto;">
        <div v-if="pickerLoading" class="text-center py-8">
          <v-progress-circular indeterminate size="28"></v-progress-circular>
        </div>
        <v-list v-else-if="filteredTools.length > 0" density="compact">
          <v-list-item
            v-for="tool in filteredTools"
            :key="tool.name"
            rounded="md"
            class="ma-1 list-item-clickable"
            @click="toggleTool(tool.name)">
            <template v-slot:prepend>
              <v-checkbox-btn
                :model-value="pickerSelected.includes(tool.name) || localItems.includes(tool.name)"
                :disabled="localItems.includes(tool.name)"
                @click.stop="toggleTool(tool.name)"
              ></v-checkbox-btn>
            </template>
            <v-list-item-title class="item-text tool-name">{{ tool.name }}</v-list-item-title>
            <v-list-item-subtitle class="tool-sub">
              <span v-if="tool.origin_display_name" class="tool-origin">{{ tool.origin_display_name }}</span>
              <span v-if="tool.description"> · {{ shortDescription(tool.description) }}</span>
            </v-list-item-subtitle>
          </v-list-item>
        </v-list>
        <div v-else class="text-center py-8 text-grey">
          {{ t('core.common.list.pickToolsEmpty') }}
        </div>
      </v-card-text>

      <v-card-actions class="pa-4">
        <span class="text-caption" style="opacity: .7">
          {{ t('core.common.list.pickToolsSelected', { count: pickerSelected.length }) }}
        </span>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="showPicker = false">{{ t('core.common.cancel') }}</v-btn>
        <v-btn
          color="primary"
          variant="tonal"
          :disabled="pickerSelected.length === 0"
          @click="confirmPicker">
          {{ t('core.common.confirm') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Batch Import Dialog -->
  <v-dialog v-model="showBatchImport" max-width="600px">
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">
        {{ t('core.common.list.batchImportTitle') }}
      </v-card-title>
      
      <v-card-text>
        <v-textarea
          v-model="batchImportText"
          :class="{ 'secret-textarea': secret && !secretVisible }"
          :append-inner-icon="secretToggleIcon"
          :autocomplete="secret ? 'new-password' : undefined"
          @click:append-inner="secretVisible = !secretVisible"
          :label="t('core.common.list.batchImportLabel')"
          :placeholder="t('core.common.list.batchImportPlaceholder')"
          rows="10"
          variant="outlined"
          :hint="t('core.common.list.batchImportHint')"
          persistent-hint
        ></v-textarea>
      </v-card-text>

      <v-card-actions class="pa-4">
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="cancelBatchImport">{{ t('core.common.cancel') }}</v-btn>
        <v-btn color="primary" variant="tonal" @click="confirmBatchImport">
          {{ t('core.common.list.batchImportButton', { count: batchImportPreviewCount }) }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useI18n } from '@/i18n/composables'
import { toolApi } from '@/api/v1'

const { t } = useI18n()

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  },
  label: {
    type: String,
    default: ''
  },
  buttonText: {
    type: String,
    default: ''
  },
  dialogTitle: {
    type: String,
    default: ''
  },
  maxDisplayItems: {
    type: Number,
    default: 1
  },
  preferSingleItem: {
    type: Boolean,
    default: true
  },
  secret: {
    type: Boolean,
    default: false
  },
  // '' | 'tools'. 'tools' adds a picker fed by the dashboard's tool registry:
  // the field holds internal identifiers, so a reader cannot be expected to
  // type them from memory.
  picker: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:modelValue'])

const dialog = ref(false)
const localItems = ref([])
const originalItems = ref([])
const newItem = ref('')
const editIndex = ref(-1)
const editItem = ref('')
const showBatchImport = ref(false)
const batchImportText = ref('')
const secretVisible = ref(false)
// A picker field is edited through its dialog, so the single-line shortcut must
// not take over when the list happens to be short.
const isSingleItemMode = computed(() => !props.picker && (props.modelValue?.length ?? 0) <= 1 && props.preferSingleItem)
const secretInputType = computed(() => props.secret && !secretVisible.value ? 'password' : 'text')
const secretToggleIcon = computed(() => {
  if (!props.secret) return undefined
  return secretVisible.value ? 'mdi-eye-off-outline' : 'mdi-eye-outline'
})
const singleItemValue = computed({
  get: () => props.modelValue?.[0] ?? '',
  set: (value) => {
    // 仅当值为完全空字符串（未输入任何字符）时清空数组，
    // 允许包含空格（如 "hello world"）以及纯空格（如 " "）通过
    if (value === '') {
      emit('update:modelValue', [])
      return
    }

    const newItems = [...(props.modelValue || [])]
    if (newItems.length === 0) {
      newItems.push(value)
    } else {
      newItems[0] = value
    }

    emit('update:modelValue', newItems)
  }
})

// 计算要显示的项目
const displayItems = computed(() => {
  return props.modelValue.slice(0, props.maxDisplayItems)
})

// 计算批量导入的项目数量
const batchImportPreviewCount = computed(() => {
  if (!batchImportText.value) return 0
  return batchImportText.value
    .split('\n')
    .map(line => line.trim())
    .filter(line => line.length > 0)
    .length
})

// 监听 modelValue 变化，同步到 localItems，并清理空字符串
watch(() => props.modelValue, (newValue) => {
  localItems.value = [...(newValue || [])]
  
  // 自动清理只包含空字符串或纯空格的条目（纯空格在配置中无意义，此过滤为预期兜底行为）
  if (newValue && newValue.length > 0) {
    const filtered = newValue.filter(item => typeof item === 'string' ? item.trim() !== '' : true)
    if (filtered.length !== newValue.length) {
      // 使用 nextTick 确保父组件已准备好接收更新
      nextTick(() => {
        emit('update:modelValue', filtered)
      })
    }
  }
}, { immediate: true })

function openDialog() {
  localItems.value = [...(props.modelValue || [])]
  originalItems.value = [...(props.modelValue || [])]
  dialog.value = true
  editIndex.value = -1
  editItem.value = ''
  newItem.value = ''
}

function addItem() {
  if (newItem.value.trim() !== '') {
    localItems.value.push(newItem.value.trim())
    newItem.value = ''
  }
}

function removeItem(index) {
  localItems.value.splice(index, 1)
}

function startEdit(index, item) {
  editIndex.value = index
  editItem.value = item
}

function saveEdit() {
  if (editItem.value.trim() !== '') {
    localItems.value[editIndex.value] = editItem.value.trim()
    cancelEdit()
  }
}

function cancelEdit() {
  editIndex.value = -1
  editItem.value = ''
}

function confirmDialog() {
  // 过滤空字符串，同时处理非字符串类型
  const filteredItems = localItems.value.filter(item => typeof item === 'string' ? item.trim() !== '' : true)
  emit('update:modelValue', filteredItems)
  dialog.value = false
}

function cancelDialog() {
  localItems.value = [...originalItems.value]
  editIndex.value = -1
  editItem.value = ''
  newItem.value = ''
  dialog.value = false
}

function confirmBatchImport() {
  if (batchImportText.value.trim()) {
    const newItems = batchImportText.value
      .split('\n')
      .map(line => line.trim())
      .filter(line => line.length > 0)
    
    localItems.value.push(...newItems)
    batchImportText.value = ''
    showBatchImport.value = false
  }
}

function cancelBatchImport() {
  batchImportText.value = ''
  showBatchImport.value = false
}

// ---- tool picker ---------------------------------------------------------
// The list above stays the source of truth: the picker only appends what is
// ticked, and anything already listed is shown ticked and disabled so a second
// visit cannot silently drop a name that a disabled plugin still needs.
const showPicker = ref(false)
const pickerSearch = ref('')
const pickerLoading = ref(false)
const pickerError = ref('')
const pickerTools = ref([])
const pickerSelected = ref([])

const filteredTools = computed(() => {
  const query = pickerSearch.value.trim().toLowerCase()
  if (!query) return pickerTools.value
  return pickerTools.value.filter(tool =>
    (tool.name || '').toLowerCase().includes(query)
    || (tool.description || '').toLowerCase().includes(query)
  )
})

function shortDescription(text) {
  const flat = String(text || '').replace(/\s+/g, ' ').trim()
  return flat.length > 90 ? flat.slice(0, 90) + '…' : flat
}

async function loadTools() {
  pickerLoading.value = true
  pickerError.value = ''
  try {
    const data = await toolApi.list()
    const rows = Array.isArray(data) ? data : []
    pickerTools.value = rows
      .map(tool => ({
        name: tool?.name || '',
        description: tool?.description || '',
        origin_display_name: tool?.origin_display_name || ''
      }))
      .filter(tool => tool.name)
      .sort((a, b) => a.name.localeCompare(b.name))
  } catch (err) {
    pickerError.value = t('core.common.list.pickToolsLoadError', {
      error: err?.message || String(err)
    })
  } finally {
    pickerLoading.value = false
  }
}

function openPicker() {
  showPicker.value = true
  pickerSearch.value = ''
  pickerSelected.value = []
  // The registry changes as plugins are reloaded, so each visit asks again;
  // the previous answer only avoids an empty dialog while the request lands.
  loadTools()
}

function toggleTool(name) {
  if (localItems.value.includes(name)) return
  const index = pickerSelected.value.indexOf(name)
  if (index >= 0) pickerSelected.value.splice(index, 1)
  else pickerSelected.value.push(name)
}

function confirmPicker() {
  for (const name of pickerSelected.value) {
    if (!localItems.value.includes(name)) localItems.value.push(name)
  }
  pickerSelected.value = []
  showPicker.value = false
}
</script>

<style scoped>
.v-list-item {
  transition: all 0.2s ease;
}

.list-item-clickable {
  cursor: pointer;
}

.list-item-clickable:hover {
  background-color: rgba(var(--v-theme-primary), 0.08);
}

.item-text {
  user-select: none;
}

/* Tool names are identifiers; a proportional font makes them harder to scan
   than the list of sentences they sit in. */
.tool-name {
  font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
  font-size: 0.86rem;
}

.tool-sub {
  font-size: 0.76rem !important;
  opacity: 0.85;
}

.tool-origin {
  color: rgb(var(--v-theme-primary));
}

.v-chip {
  margin: 2px;
}

.secret-textarea :deep(textarea) {
  -webkit-text-security: disc;
}
</style>
