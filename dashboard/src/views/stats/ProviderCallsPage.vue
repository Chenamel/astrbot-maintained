<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RefreshCw, RotateCcw } from "@lucide/vue";
import { statsApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";

const { tm } = useModuleI18n("features/calls");

interface CallItem {
  id: number;
  created_at: string;
  agent_type: string;
  caller?: string | null;
  umo: string | null;
  umo_display?: string | null;
  platform_type?: string | null;
  provider_id: string | null;
  provider_model: string | null;
  status: string;
  token_input_other: number;
  token_input_cached: number;
  token_output: number;
  total_tokens: number;
  duration_ms: number | null;
  ttft_ms: number | null;
}

interface CallSummary {
  total_calls: number;
  token_input_other: number;
  token_input_cached: number;
  token_output: number;
  total_tokens: number;
  success_rate: number;
}

const loading = ref(false);
const items = ref<CallItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(50);
const jumpPage = ref<number | null>(null);
const summary = ref<CallSummary>({
  total_calls: 0,
  token_input_other: 0,
  token_input_cached: 0,
  token_output: 0,
  total_tokens: 0,
  success_rate: 0,
});

const agentTypeOptions = [
  { value: "", label: "all" },
  { value: "internal", label: "internal" },
  { value: "llm_generate", label: "llmGenerate" },
  { value: "proactive_persona", label: "proactivePersona" },
];
const statusOptions = ["completed", "error", "aborted"];

const quickRanges = ["today", "yesterday", "3d", "7d", "30d", "month", "all"];
const quickRange = ref("7d");
const startDate = ref("");
const endDate = ref("");
const modelFilter = ref("");
const sessionFilter = ref("");
const agentFilter = ref("");
const callerFilter = ref("");
const callerItems = ref<string[]>([]);
const statusFilter = ref("");

const detailOpen = ref(false);
const detailItem = ref<CallItem | null>(null);

function openDetail(item: CallItem) {
  detailItem.value = item;
  detailOpen.value = true;
}
const modelItems = ref<string[]>([]);
const sessionItems = ref<string[]>([]);
// display name -> raw umo, so a picked alias still filters by umo.
const sessionLookup = ref<Record<string, string>>({});

function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function applyQuickRange(range: string) {
  const now = new Date();
  const today = isoDate(now);
  if (range === "today") {
    startDate.value = `${today}T00:00`;
    endDate.value = `${today}T23:59`;
  } else if (range === "yesterday") {
    const y = isoDate(new Date(now.getTime() - 86400000));
    startDate.value = `${y}T00:00`;
    endDate.value = `${y}T23:59`;
  } else if (range === "3d" || range === "7d" || range === "30d") {
    const days = range === "3d" ? 3 : range === "7d" ? 7 : 30;
    const from = isoDate(new Date(now.getTime() - (days - 1) * 86400000));
    startDate.value = `${from}T00:00`;
    endDate.value = `${today}T23:59`;
  } else if (range === "month") {
    const first = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
    startDate.value = `${first}T00:00`;
    endDate.value = `${today}T23:59`;
  } else {
    startDate.value = "";
    endDate.value = "";
  }
}

watch(quickRange, applyQuickRange);

async function load() {
  loading.value = true;
  try {
    const params: Record<string, unknown> = {
      page: page.value,
      page_size: pageSize.value,
    };
    // datetime-local already carries the hour, so the range is hourly-grained.
    if (startDate.value) {
      params.start = startDate.value;
    }
    if (endDate.value) {
      params.end = endDate.value;
    }
    if (modelFilter.value.trim()) {
      params.provider_model = modelFilter.value.trim();
    }
    const session = typeof sessionFilter.value === "string" ? sessionFilter.value.trim() : "";
    if (session) {
      params.umo = sessionLookup.value[session] || session;
    }
    if (agentFilter.value) {
      params.agent_type = agentFilter.value;
    }
    if (callerFilter.value) {
      params.caller = callerFilter.value;
    }
    if (statusFilter.value) {
      params.status = statusFilter.value;
    }
    const resp = await statsApi.providerCalls(params);
    const payload = resp.data?.data ?? {};
    items.value = payload.items ?? [];
    total.value = payload.total ?? 0;
    summary.value = payload.summary ?? summary.value;
    const known = new Set(modelItems.value);
    const knownSessions = new Set(sessionItems.value);
    const knownCallers = new Set(callerItems.value);
    for (const item of items.value) {
      if (item.provider_model) known.add(item.provider_model);
      if (item.caller) knownCallers.add(item.caller);
      if (item.umo) {
        const label = item.umo_display || item.umo;
        knownSessions.add(label);
        sessionLookup.value[label] = item.umo;
      }
    }
    modelItems.value = [...known].sort();
    callerItems.value = [...knownCallers].sort();
    sessionItems.value = [...knownSessions].sort();
  } finally {
    loading.value = false;
  }
}

function search() {
  page.value = 1;
  load();
}

function changeSize(size: number) {
  pageSize.value = size;
  search();
}

function jumpTo() {
  const target = jumpPage.value;
  if (target === null) return;
  const clamped = Math.min(Math.max(1, Math.floor(target)), totalPages.value);
  page.value = clamped;
  jumpPage.value = clamped;
  load();
}

function reset() {
  modelFilter.value = "";
  sessionFilter.value = "";
  agentFilter.value = "";
  callerFilter.value = "";
  statusFilter.value = "";
  quickRange.value = "7d";
  applyQuickRange("7d");
  search();
}

function gotoPage(delta: number) {
  const next = page.value + delta;
  if (next < 1 || (delta > 0 && next > totalPages.value)) return;
  page.value = next;
  load();
}

const totalPages = computed(() =>
  Math.max(1, Math.ceil(total.value / pageSize.value)),
);

const agentLabel = (type: string): string => {
  const option = agentTypeOptions.find((o) => o.value === type);
  return option ? tm(`source.${option.label}`) : type;
};

const fmtNumber = (n: number): string => n.toLocaleString();
const fmtMs = (ms: number | null): string =>
  ms === null ? "—" : `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)}s`;
const callerLabel = (caller?: string | null): string =>
  caller ? caller.split("|").join(" / ") : "";
const statusText = (status: string): string => tm(`status.${status}`);
const statusColor = (status: string): string =>
  status === "error" ? "error" : status === "aborted" ? "warning" : "success";

onMounted(() => {
  applyQuickRange(quickRange.value);
  load();
});
</script>

<template>
  <div class="calls-page">
    <section class="stat-card filter-card">
      <div class="filter-row">
        <div class="quick-chips">
          <button
            v-for="range in quickRanges"
            :key="range"
            class="quick-chip"
            :class="{ 'quick-chip--active': quickRange === range }"
            type="button"
            @click="quickRange = range"
          >
            {{ tm(`quick.${range}`) }}
          </button>
        </div>
        <div class="filter-fields">
          <input v-model="startDate" type="datetime-local" class="date-input" aria-label="start" />
          <span class="date-sep">→</span>
          <input v-model="endDate" type="datetime-local" class="date-input" aria-label="end" />
          <v-combobox
            v-model="modelFilter"
            :items="modelItems"
            :label="tm('filters.model')"
            density="compact"
            hide-details
            clearable
            variant="outlined"
            class="filter-field"
          />
          <v-combobox
            v-model="sessionFilter"
            :items="sessionItems"
            :label="tm('filters.session')"
            density="compact"
            hide-details
            clearable
            variant="outlined"
            class="filter-field"
          />
          <v-select
            v-model="agentFilter"
            :items="agentTypeOptions.map((o) => ({ title: tm(`source.${o.label}`), value: o.value }))"
            :label="tm('filters.source')"
            density="compact"
            hide-details
            clearable
            variant="outlined"
            class="filter-field"
          />
          <v-combobox
            v-if="agentFilter === 'llm_generate'"
            v-model="callerFilter"
            :items="callerItems"
            :label="tm('filters.plugin')"
            density="compact"
            hide-details
            clearable
            variant="outlined"
            class="filter-field"
          />
          <v-select
            v-model="statusFilter"
            :items="statusOptions.map((s) => ({ title: statusText(s), value: s }))"
            :label="tm('filters.status')"
            density="compact"
            hide-details
            clearable
            variant="outlined"
            class="filter-field"
          />
          <div class="filter-actions">
            <v-btn color="primary" density="comfortable" :loading="loading" @click="search">
              {{ tm('filters.search') }}
            </v-btn>
            <v-tooltip :text="tm('toolbar.reset')" location="top">
              <template #activator="{ props: tip }">
                <v-btn v-bind="tip" variant="text" density="comfortable" :icon="RotateCcw" @click="reset" />
              </template>
            </v-tooltip>
            <v-tooltip :text="tm('toolbar.refresh')" location="top">
              <template #activator="{ props: tip }">
                <v-btn v-bind="tip" variant="text" density="comfortable" :icon="RefreshCw" @click="load" />
              </template>
            </v-tooltip>
          </div>
        </div>
      </div>
    </section>

    <section class="summary-row">
      <div class="stat-card summary-cell">
        <div class="summary-label">{{ tm('summary.calls') }}</div>
        <div class="summary-value">{{ fmtNumber(summary.total_calls) }}</div>
      </div>
      <div class="stat-card summary-cell">
        <div class="summary-label">{{ tm('summary.input') }}</div>
        <div class="summary-value">{{ fmtNumber(summary.token_input_other) }}</div>
      </div>
      <div class="stat-card summary-cell">
        <div class="summary-label">{{ tm('summary.cached') }}</div>
        <div class="summary-value">{{ fmtNumber(summary.token_input_cached) }}</div>
      </div>
      <div class="stat-card summary-cell">
        <div class="summary-label">{{ tm('summary.output') }}</div>
        <div class="summary-value">{{ fmtNumber(summary.token_output) }}</div>
      </div>
      <div class="stat-card summary-cell summary-cell--wide">
        <div class="summary-label">{{ tm('summary.total') }}</div>
        <div class="summary-value">{{ fmtNumber(summary.total_tokens) }}</div>
      </div>
      <div class="stat-card summary-cell">
        <div class="summary-label">{{ tm('summary.successRate') }}</div>
        <div class="summary-value">{{ (summary.success_rate * 100).toFixed(1) }}%</div>
      </div>
    </section>

    <section class="stat-card table-card">
      <div class="v-table-wrap">
        <v-table density="comfortable" class="calls-table">
          <thead>
            <tr>
              <th>{{ tm('table.time') }}</th>
              <th>{{ tm('table.source') }}</th>
              <th>{{ tm('table.session') }}</th>
              <th>{{ tm('table.model') }}</th>
              <th class="num">{{ tm('table.input') }}</th>
              <th class="num">{{ tm('table.cached') }}</th>
              <th class="num">{{ tm('table.output') }}</th>
              <th class="num">{{ tm('table.total') }}</th>
              <th class="num">{{ tm('table.duration') }}</th>
              <th class="num">{{ tm('table.ttft') }}</th>
              <th>{{ tm('table.status') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in items"
              :key="item.id"
              class="call-row"
              @click="openDetail(item)"
            >
              <td class="mono">{{ item.created_at.replace('T', ' ') }}</td>
              <td>
                <span class="type-chip">{{ callerLabel(item.caller) || agentLabel(item.agent_type) }}</span>
              </td>
              <td class="session-cell" :title="item.umo || ''">{{ item.umo_display || item.umo || '—' }}</td>
              <td class="model-cell">{{ item.provider_model || '—' }}</td>
              <td class="num">{{ fmtNumber(item.token_input_other) }}</td>
              <td class="num muted">{{ fmtNumber(item.token_input_cached) }}</td>
              <td class="num">{{ fmtNumber(item.token_output) }}</td>
              <td class="num strong">{{ fmtNumber(item.total_tokens) }}</td>
              <td class="num">{{ fmtMs(item.duration_ms) }}</td>
              <td class="num">{{ fmtMs(item.ttft_ms) }}</td>
              <td>
                <v-chip :color="statusColor(item.status)" size="x-small" label>
                  {{ statusText(item.status) }}
                </v-chip>
              </td>
            </tr>
            <tr v-if="!items.length && !loading">
              <td colspan="11" class="empty-cell">{{ tm('table.empty') }}</td>
            </tr>
          </tbody>
        </v-table>
      </div>
      <div class="pager">
        <span class="pager-info">
          {{ tm('pager.total', { n: fmtNumber(total) }) }}
        </span>
        <v-select
          :model-value="pageSize"
          :items="[25, 50, 100, 200]"
          :label="tm('pager.size')"
          density="compact"
          hide-details
          variant="outlined"
          style="max-width: 110px"
          @update:model-value="changeSize"
        />
        <v-text-field
          v-model="jumpPage"
          type="number"
          min="1"
          :max="totalPages"
          :label="tm('pager.jump')"
          density="compact"
          hide-details
          variant="outlined"
          style="max-width: 110px"
          @keyup.enter="jumpTo"
        />
        <v-btn variant="tonal" size="small" :disabled="loading" @click="jumpTo">
          {{ tm('pager.go') }}
        </v-btn>
        <v-btn
          variant="tonal"
          size="small"
          :disabled="page <= 1 || loading"
          @click="gotoPage(-1)"
        >
          {{ tm('pager.prev') }}
        </v-btn>
        <span class="pager-page">{{ page }} / {{ totalPages }}</span>
        <v-btn
          variant="tonal"
          size="small"
          :disabled="page >= totalPages || loading"
          @click="gotoPage(1)"
        >
          {{ tm('pager.next') }}
        </v-btn>
      </div>
    </section>

    <v-dialog v-model="detailOpen" max-width="560">
      <v-card v-if="detailItem" class="detail-card">
        <v-card-title class="d-flex align-center ga-2">
          {{ tm('detail.title') }}
          <v-chip :color="statusColor(detailItem.status)" size="x-small" label>
            {{ statusText(detailItem.status) }}
          </v-chip>
        </v-card-title>
        <v-card-text>
          <div class="detail-grid">
            <template v-for="row in [
                ['time', detailItem.created_at.replace('T', ' ')],
                ['source', agentLabel(detailItem.agent_type)],
                ['caller', callerLabel(detailItem.caller) || '—'],
                ['session', detailItem.umo_display || detailItem.umo || '—'],
                ['rawUmo', detailItem.umo || '—'],
                ['model', detailItem.provider_model || '—'],
                ['provider', detailItem.provider_id || '—'],
                ['input', fmtNumber(detailItem.token_input_other)],
                ['cached', fmtNumber(detailItem.token_input_cached)],
                ['output', fmtNumber(detailItem.token_output)],
                ['total', fmtNumber(detailItem.total_tokens)],
                ['duration', fmtMs(detailItem.duration_ms)],
                ['ttft', fmtMs(detailItem.ttft_ms)],
                ['id', String(detailItem.id)],
              ]" :key="row[0]"
            >
              <div class="detail-key">{{ tm(`detail.${row[0]}`) }}</div>
              <div class="detail-val mono">{{ row[1] }}</div>
            </template>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="detailOpen = false">{{ tm('detail.close') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.calls-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stat-card {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  padding: 16px;
}

.filter-row {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.quick-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.quick-chip {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  border-radius: 999px;
  padding: 4px 14px;
  font-size: 13px;
  cursor: pointer;
}

.quick-chip--active {
  background: rgb(var(--v-theme-primary));
  border-color: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}

.filter-fields {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

/* Keeps the action buttons together on one line even when the filters wrap. */
.filter-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
  margin-left: auto;
}

.filter-field {
  min-width: 130px;
  max-width: 190px;
  flex: 1 1 130px;
}

.date-input {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  padding: 6px 8px;
  font-size: 12px;
  flex: 0 1 190px;
  min-width: 170px;
}

.date-sep {
  opacity: 0.6;
}

.summary-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

@media (min-width: 900px) {
  .summary-row {
    grid-template-columns: repeat(6, 1fr);
  }
}

.summary-cell--wide {
  grid-column: span 2;
}

@media (min-width: 900px) {
  .summary-cell--wide {
    grid-column: span 1;
  }
}

.summary-label {
  font-size: 12px;
  opacity: 0.7;
}

.summary-value {
  font-size: 20px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.v-table-wrap {
  overflow-x: auto;
}

.calls-table {
  width: 100%;
  font-size: 13px;
}

.calls-table th {
  white-space: nowrap;
  font-weight: 600;
}

.calls-table td {
  white-space: nowrap;
}

.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.mono {
  font-family: monospace;
  font-size: 12px;
}

.muted {
  opacity: 0.65;
}

.strong {
  font-weight: 600;
}

.type-chip {
  font-size: 12px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 6px;
  padding: 1px 8px;
}

.session-cell,
.model-cell {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.call-row {
  cursor: pointer;
}

.call-row:hover {
  background: rgba(var(--v-theme-primary), 0.06);
}

.empty-cell {
  text-align: center;
  opacity: 0.6;
  padding: 32px 0;
}

.pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 12px;
}

.pager-info {
  opacity: 0.7;
  font-size: 13px;
  margin-right: auto;
}

.pager-page {
  font-variant-numeric: tabular-nums;
  font-size: 13px;
}

.detail-card {
  border-radius: 12px;
}

.detail-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px 16px;
  font-size: 13px;
}

.detail-key {
  opacity: 0.65;
}

.detail-val {
  word-break: break-all;
}
</style>
