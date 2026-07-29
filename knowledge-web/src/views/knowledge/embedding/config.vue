<template>
  <div class="app-container embedding-config" v-loading="pageLoading">
    <el-page-header @back="handleCancel" content="Embedding 配置" class="mb16" />
    <div class="doc-meta-line">
      <span>文档 ID：{{ docId || "-" }}</span>
      <span class="meta-sep">·</span>
      <span>标题：{{ docInfo.docTitle || "-" }}</span>
      <span class="meta-sep">·</span>
      <span>模型：{{ modelInfo.modelCode || "-" }}</span>
      <span class="meta-sep">·</span>
      <span>维度：{{ modelInfo.dimensions ?? "-" }}</span>
    </div>

    <el-row :gutter="16" class="config-main-row">
      <el-col :span="8" class="config-left">
        <el-card shadow="never" class="mb16">
          <template #header>
            <span>切分策略</span>
          </template>
          <el-radio-group v-model="form.splitType" class="strategy-radio-group" @change="handleStrategyChange">
            <el-radio
              v-for="item in strategies"
              :key="item.code"
              :value="item.code"
              class="strategy-radio"
            >
              {{ item.name || item.code }}
            </el-radio>
          </el-radio-group>
        </el-card>

        <el-card shadow="never" class="mb16">
          <template #header>
            <span>切分参数</span>
          </template>
          <el-form ref="paramRef" :model="form" :rules="paramRules" label-width="100px">
            <el-form-item label="块大小" prop="chunkSize">
              <el-input-number
                v-model="form.chunkSize"
                :min="1"
                :max="chunkSizeMax"
                controls-position="right"
                style="width: 100%"
              />
              <div class="param-hint">上限 {{ chunkSizeMax }}（对齐精排单文档字符上限）</div>
            </el-form-item>
            <el-form-item v-if="showOverlap" prop="overlap">
              <template #label>
                <span>重叠长度</span>
              </template>
              <el-input-number v-model="form.overlap" :min="0" :max="form.chunkSize" controls-position="right" style="width: 100%" />
              <div v-if="showTitleLevel" class="param-hint">
                仅在「单段超过块大小」后的子块之间生效；标题与标题切开的普通块互不重叠。
              </div>
            </el-form-item>
            <el-form-item v-if="showTitleLevel" label="标题层级" prop="titleLevel">
              <el-input-number v-model="form.titleLevel" :min="1" :max="6" controls-position="right" style="width: 100%" />
            </el-form-item>
            <el-form-item v-if="showSeparator" label="分隔符" prop="separator">
              <el-select v-model="form.separator" placeholder="请选择分隔符" style="width: 100%">
                <el-option
                  v-for="dict in document_split_separator"
                  :key="dict.value"
                  :label="dict.label"
                  :value="dict.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item v-if="showRegex" label="正则表达式" prop="regex">
              <el-select
                :model-value="matchedRegexTemplate"
                clearable
                filterable
                placeholder="选择常用模板（可选）"
                style="width: 100%"
                class="regex-template-select"
                @change="handleRegexTemplateChange"
              >
                <el-option
                  v-for="dict in document_split_regex_template"
                  :key="dict.value"
                  :label="dict.label"
                  :value="dict.value"
                >
                  <div class="regex-option">
                    <span class="regex-option-label">{{ dict.label }}</span>
                    <span class="regex-option-pattern">{{ dict.value }}</span>
                  </div>
                </el-option>
              </el-select>
              <el-input
                v-model="form.regex"
                type="textarea"
                :rows="2"
                placeholder="请输入正则表达式，或从上方模板填入后修改"
              />
              <div class="param-hint">
                匹配到的分隔内容默认会被丢掉；题号/FAQ/日志等「前瞻」模板会保留标记在下一块开头。
              </div>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card v-if="currentStrategy" shadow="never" class="mb16 strategy-help-card">
          <template #header>
            <span>策略说明</span>
          </template>
          <p class="strategy-summary">{{ currentStrategy.summary }}</p>
          <el-collapse v-model="strategyHelpActive" class="strategy-help-collapse">
            <el-collapse-item
              v-if="currentStrategy.processSteps?.length"
              title="切分过程"
              name="process"
            >
              <ol class="strategy-list strategy-process">
                <li v-for="(step, idx) in currentStrategy.processSteps" :key="`s-${idx}`">{{ step }}</li>
              </ol>
            </el-collapse-item>
            <el-collapse-item
              v-if="currentStrategy.paramNotes?.length"
              title="参数说明"
              name="params"
            >
              <ul class="strategy-list">
                <li v-for="(note, idx) in currentStrategy.paramNotes" :key="`p-${idx}`">{{ note }}</li>
              </ul>
            </el-collapse-item>
            <el-collapse-item
              v-if="currentStrategy.applicableScenes?.length"
              title="适用场景"
              name="scenes"
            >
              <div class="strategy-scene-tags">
                <el-tag
                  v-for="(scene, idx) in currentStrategy.applicableScenes"
                  :key="idx"
                  size="small"
                  type="info"
                  effect="plain"
                >{{ scene }}</el-tag>
              </div>
            </el-collapse-item>
            <el-collapse-item
              v-if="currentStrategy.notes?.length"
              title="注意事项"
              name="notes"
            >
              <ul class="strategy-list">
                <li v-for="(note, idx) in currentStrategy.notes" :key="`n-${idx}`">{{ note }}</li>
              </ul>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </el-col>

      <el-col :span="16" class="config-right">
        <div class="footer-actions">
          <el-button type="primary" plain icon="View" :loading="previewLoading" @click="handlePreview">
            预览切分效果
          </el-button>
          <el-button @click="handleCancel">取 消</el-button>
          <el-button type="primary" :loading="submitLoading" v-hasPermi="['rag:embedding:create']" @click="handleSubmit">
            提交任务
          </el-button>
        </div>

        <el-card shadow="never" class="preview-card">
          <template #header>
            <div class="preview-header">
              <span>{{ previewLoaded ? "效果预览" : "原文" }}</span>
              <el-select
                v-if="isCrawlSource"
                v-model="selectedFileId"
                placeholder="选择预览页面"
                style="width: 280px"
                size="small"
                fit-input-width
                popper-class="embedding-file-select-popper"
              >
                <el-option
                  v-for="file in fileList"
                  :key="file.id"
                  :label="fileLabel(file)"
                  :value="file.id"
                  :title="fileLabel(file)"
                >
                  <span class="file-option-label">{{ fileLabel(file) }}</span>
                </el-option>
              </el-select>
            </div>
          </template>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            class="preview-tip"
          >
            <template #title>
              <div v-if="!previewLoaded">
                先查看原文，调好切分参数后点击「预览切分效果」，将与原文左右对照。
              </div>
              <template v-else>
                <div>
                  父子块 ≠ 标题层级（# / ## 仍是平铺的独立块）。只有「单段超过块大小」时才会出现：外框父块（不入向量库）+ 内嵌子块（入向量库）。
                </div>
                <div class="preview-tip-sub">左侧：切分结果（黄底=重叠区）；右侧：连续原文（着色=对应分块，便于看切点）。仅展示前 20 个可向量化分块，提交后全量切分。</div>
              </template>
            </template>
          </el-alert>
          <div v-if="previewResult" class="preview-meta">
            <el-tag v-if="previewResult.sampleTruncated" type="warning" size="small">样本已截断</el-tag>
            <span class="preview-meta-text">样本长度：{{ previewResult.sampleLength ?? 0 }}</span>
            <span class="preview-meta-text">
              可向量化：{{ embeddableSegmentCount }}，展示：{{ displayEmbeddableCount }}
            </span>
            <el-button
              v-if="displayParentCount"
              type="warning"
              link
              size="small"
              @click="scrollToFirstParent"
            >
              父块组 {{ displayParentCount }}（点击定位）
            </el-button>
            <span v-else class="preview-meta-text">当前预览无父块（把块大小调小更容易出现）</span>
          </div>

          <!-- 已预览：切分效果 | 原文 -->
          <div v-if="displayGroups.length" class="compare-preview">
            <div class="compare-pane">
              <div class="compare-pane-title">切分效果</div>
              <div
                ref="chunkScrollRef"
                class="article-preview chunk-list-preview"
                @scroll="handleChunkScroll"
              >
                <template v-for="(group, gIdx) in displayGroups" :key="`chunk-g-${gIdx}`">
                  <div
                    v-if="group.type === 'family'"
                    :ref="(el) => setParentBlockRef(gIdx, el)"
                    class="parent-block"
                    :class="{ 'is-flash': flashParentIdx === gIdx }"
                  >
                    <div class="parent-block-header">
                      <span class="role-tag is-parent">父块 · 不入向量库</span>
                      <span class="parent-meta">
                        {{ group.parent.length ?? (group.parent.text || "").length }} 字 · 切成
                        {{ group.children.length }} 个子块
                      </span>
                      <el-button link type="primary" size="small" @click="toggleParent(gIdx)">
                        {{ isParentExpanded(gIdx) ? "收起全文" : "展开全文" }}
                      </el-button>
                    </div>
                    <div class="parent-block-summary">{{ parentSummary(group.parent.text) }}</div>
                    <div v-show="isParentExpanded(gIdx)" class="parent-block-body">{{ group.parent.text || "" }}</div>
                    <div class="child-list">
                      <div
                        v-for="(child, cIdx) in group.children"
                        :key="`chunk-c-${gIdx}-${cIdx}`"
                        class="chunk-block is-child"
                      >
                        <span
                          class="chunk-mark"
                          :style="{ color: chunkColor(child.colorIndex), borderColor: chunkColor(child.colorIndex) }"
                        >子块{{ child.colorIndex + 1 }}</span>
                        <span class="role-tag is-child-tag">入向量库</span>
                        <span class="chunk-text" :style="{ color: chunkColor(child.colorIndex) }">
                          <span
                            v-for="(part, pIdx) in overlapParts(child)"
                            :key="pIdx"
                            :class="{ 'is-overlap': part.isOverlap }"
                            :title="part.isOverlap ? '重叠区' : undefined"
                          >{{ part.text }}</span>
                        </span>
                      </div>
                    </div>
                  </div>
                  <div v-else class="chunk-block">
                    <span
                      class="chunk-mark"
                      :style="{ color: chunkColor(group.seg.colorIndex), borderColor: chunkColor(group.seg.colorIndex) }"
                    >块{{ group.seg.colorIndex + 1 }}</span>
                    <span class="chunk-text" :style="{ color: chunkColor(group.seg.colorIndex) }">
                      <span
                        v-for="(part, pIdx) in overlapParts(group.seg)"
                        :key="pIdx"
                        :class="{ 'is-overlap': part.isOverlap }"
                        :title="part.isOverlap ? '重叠区' : undefined"
                      >{{ part.text }}</span>
                    </span>
                  </div>
                </template>
              </div>
            </div>
            <div class="compare-pane">
              <div class="compare-pane-title">原文（连续）</div>
              <div
                ref="sourceScrollRef"
                class="article-preview source-preview source-continuous"
                @scroll="handleSourceScroll"
              >
                <span
                  v-for="(part, pIdx) in sourceHighlightParts"
                  :key="`src-${pIdx}`"
                  class="source-part"
                  :class="{ 'is-chunk': part.colorIndex >= 0 }"
                  :style="part.colorIndex >= 0 ? { color: chunkColor(part.colorIndex) } : undefined"
                >{{ part.text }}</span>
              </div>
            </div>
          </div>

          <!-- 默认：只展示原文，方便对照调参 -->
          <div v-else-if="displaySourceText" class="source-only-wrap">
            <div class="compare-pane-title">原文（Markdown）</div>
            <div class="article-preview source-preview source-only">{{ displaySourceText }}</div>
          </div>
          <el-empty v-else-if="previewLoaded" description="暂无预览片段" />
          <el-empty v-else-if="sourceLoading" description="原文加载中…" />
          <el-empty v-else description="暂无原文，请确认文档已转换完成" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup name="EmbeddingConfig">
import { computed, getCurrentInstance, nextTick, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  createEmbeddingTask,
  getEmbeddingModelInfo,
  getEmbeddingStrategies,
  previewEmbedding,
} from "@/api/content/embedding";
import { listDocumentFiles, listDocumentRecord, previewDocument } from "@/api/content/document";
import { listCrawlerDocument } from "@/api/content/crawler";

const { proxy } = getCurrentInstance();
const { document_split_separator, document_split_regex_template } = proxy.useDict(
  "document_split_separator",
  "document_split_regex_template"
);

const route = useRoute();
const router = useRouter();

const docId = computed(() => {
  const raw = route.query.docId;
  return raw ? Number(raw) : null;
});
const sourceType = computed(() => String(route.query.sourceType ?? "0"));
const isCrawlSource = computed(() => sourceType.value === "1");

const pageLoading = ref(false);
const previewLoading = ref(false);
const submitLoading = ref(false);
const previewLoaded = ref(false);
const strategies = ref([]);
const strategyHelpActive = ref(["process"]);
const modelInfo = ref({});
const docInfo = ref({});
const fileList = ref([]);
const selectedFileId = ref(null);
const previewResult = ref(null);
const previewSegments = ref([]);
const sourceText = ref("");
const sourceLoading = ref(false);

const form = reactive({
  splitType: "TITLE",
  chunkSize: 500,
  overlap: 50,
  titleLevel: 2,
  separator: "\\n\\n",
  regex: "",
});

const paramRef = ref(null);
const sourceScrollRef = ref(null);
const chunkScrollRef = ref(null);
let syncingScroll = false;

const currentStrategy = computed(() =>
  strategies.value.find((s) => s.code === form.splitType)
);

/** 块大小上限：来自策略 paramSchema.chunkSize.maximum（sys_config rag.rerank.max_doc_chars） */
const chunkSizeMax = computed(() => {
  const schema = currentStrategy.value?.paramSchema;
  const props = schema?.properties || schema || {};
  const max = props.chunkSize?.maximum;
  return Number.isFinite(Number(max)) && Number(max) > 0 ? Number(max) : 4000;
});

function syncScroll(fromEl, toEl) {
  if (!fromEl || !toEl || syncingScroll) return;
  const fromMax = fromEl.scrollHeight - fromEl.clientHeight;
  const toMax = toEl.scrollHeight - toEl.clientHeight;
  if (fromMax <= 0 || toMax <= 0) return;
  syncingScroll = true;
  toEl.scrollTop = (fromEl.scrollTop / fromMax) * toMax;
  requestAnimationFrame(() => {
    syncingScroll = false;
  });
}

function handleSourceScroll() {
  syncScroll(sourceScrollRef.value, chunkScrollRef.value);
}

function handleChunkScroll() {
  syncScroll(chunkScrollRef.value, sourceScrollRef.value);
}

const showOverlap = computed(() => form.splitType !== "SMART");
const showTitleLevel = computed(() => form.splitType === "TITLE");
const showSeparator = computed(() => form.splitType === "SEPARATOR");
const showRegex = computed(() => form.splitType === "REGEX");

/** 当前 regex 若命中模板字典，则回显下拉选中项；手改后不匹配则清空选中态 */
const matchedRegexTemplate = computed(() => {
  const list = document_split_regex_template.value || [];
  const current = form.regex;
  if (!current) return undefined;
  return list.some((d) => d.value === current) ? current : undefined;
});

function handleRegexTemplateChange(val) {
  form.regex = val == null ? "" : String(val);
}

const paramRules = computed(() => {
  const rules = {
    chunkSize: [
      { required: true, message: "块大小不能为空", trigger: "blur" },
      {
        type: "number",
        max: chunkSizeMax.value,
        message: `块大小不能超过 ${chunkSizeMax.value}`,
        trigger: "blur",
      },
    ],
  };
  if (showTitleLevel.value) {
    rules.titleLevel = [{ required: true, message: "标题层级不能为空", trigger: "blur" }];
  }
  if (showSeparator.value) {
    rules.separator = [{ required: true, message: "请选择分隔符", trigger: "change" }];
  }
  if (showRegex.value) {
    rules.regex = [{ required: true, message: "正则表达式不能为空", trigger: "blur" }];
  }
  return rules;
});

const PREVIEW_CHUNK_LIMIT = 20;
const CHUNK_COLORS = ["#1d4ed8", "#b45309"];
const expandedParents = ref(new Set());
const flashParentIdx = ref(-1);
const parentBlockRefs = ref({});
let flashTimer = null;

const embeddableSegments = computed(() =>
  (previewSegments.value || []).filter((seg) => !seg.skipEmbedding)
);

const embeddableSegmentCount = computed(() => embeddableSegments.value.length);

/**
 * 将扁平 segments 组装为展示组：
 * - leaf：普通可向量化块
 * - family：父块（skipEmbedding）+ 其子块嵌套
 * 按可向量化块数截断到 PREVIEW_CHUNK_LIMIT。
 */
const displayGroups = computed(() => {
  const segs = previewSegments.value || [];
  if (!segs.length) return [];

  const childrenOf = new Map();
  segs.forEach((seg) => {
    if (!seg.parentChunkId) return;
    const pid = String(seg.parentChunkId);
    if (!childrenOf.has(pid)) childrenOf.set(pid, []);
    childrenOf.get(pid).push(seg);
  });

  const consumed = new Set();
  const groups = [];
  let embedCount = 0;
  let colorIndex = 0;

  for (const seg of segs) {
    const chunkId = String(seg.metadata?.chunkId || seg.chunkId || `ord-${seg.order}`);
    if (consumed.has(chunkId)) continue;

    // 子块：等父块一起处理
    if (seg.parentChunkId) continue;

    if (seg.skipEmbedding) {
      const children = (childrenOf.get(chunkId) || []).filter((c) => !c.skipEmbedding);
      const remain = PREVIEW_CHUNK_LIMIT - embedCount;
      if (remain <= 0) break;
      const shownChildren = children.slice(0, remain).map((c) => {
        const cid = String(c.metadata?.chunkId || c.chunkId || `ord-${c.order}`);
        consumed.add(cid);
        return { ...c, colorIndex: colorIndex++ };
      });
      // 同组未展示完的子块也标记已消费，避免后续当孤儿块露出
      children.forEach((c) => {
        consumed.add(String(c.metadata?.chunkId || c.chunkId || `ord-${c.order}`));
      });
      consumed.add(chunkId);
      if (!shownChildren.length) continue;
      annotateAdjacentOverlaps(shownChildren);
      embedCount += shownChildren.length;
      groups.push({ type: "family", parent: seg, children: shownChildren });
      continue;
    }

    if (embedCount >= PREVIEW_CHUNK_LIMIT) break;
    consumed.add(chunkId);
    groups.push({ type: "leaf", seg: { ...seg, colorIndex: colorIndex++, overlapPrefix: 0, overlapSuffix: 0 } });
    embedCount += 1;
  }

  annotateAdjacentLeafOverlaps(groups);
  return groups;
});

const displayEmbeddableCount = computed(() =>
  displayGroups.value.reduce((n, g) => n + (g.type === "family" ? g.children.length : 1), 0)
);

const displayParentCount = computed(() =>
  displayGroups.value.filter((g) => g.type === "family").length
);

const firstParentGroupIdx = computed(() =>
  displayGroups.value.findIndex((g) => g.type === "family")
);

/** 对照用原文：优先预览样本，否则用进页加载的全文 */
const displaySourceText = computed(() => {
  if (previewResult.value?.sampleText) return previewResult.value.sampleText;
  return sourceText.value || "";
});

/**
 * 连续原文按「当前展示的可向量化块」着色，保持文档流不断开。
 * 重叠区后写覆盖；未匹配到的样本段落保持默认色。
 */
const sourceHighlightParts = computed(() => {
  const sample = displaySourceText.value || "";
  if (!sample) return [];
  if (!displayGroups.value.length) {
    return [{ text: sample, colorIndex: -1 }];
  }

  const colors = new Array(sample.length).fill(-1);
  let searchFrom = 0;

  for (const group of displayGroups.value) {
    const segs = group.type === "family" ? group.children : [group.seg];
    for (const seg of segs) {
      const t = seg?.text || "";
      if (!t) continue;
      const slack = Math.max(seg.overlapPrefix || 0, form.overlap || 0, 0);
      const from = Math.max(0, searchFrom - slack);
      let idx = sample.indexOf(t, from);
      if (idx < 0) idx = sample.indexOf(t);
      if (idx < 0) continue;
      const end = Math.min(idx + t.length, sample.length);
      for (let i = idx; i < end; i += 1) {
        colors[i] = seg.colorIndex;
      }
      searchFrom = end;
    }
  }

  const parts = [];
  let i = 0;
  while (i < sample.length) {
    const c = colors[i];
    let j = i + 1;
    while (j < sample.length && colors[j] === c) j += 1;
    parts.push({ text: sample.slice(i, j), colorIndex: c });
    i = j;
  }
  return parts.length ? parts : [{ text: sample, colorIndex: -1 }];
});

function chunkColor(index) {
  return CHUNK_COLORS[index % CHUNK_COLORS.length];
}

/** 相邻块后缀/前缀最长公共重叠长度 */
function computeOverlapLen(prev, next) {
  if (!prev || !next) return 0;
  const max = Math.min(prev.length, next.length);
  for (let len = max; len > 0; len -= 1) {
    if (prev.endsWith(next.slice(0, len))) return len;
  }
  return 0;
}

/** 给一串相邻文本块标注首尾重叠长度 */
function annotateAdjacentOverlaps(items) {
  for (let i = 0; i < items.length; i += 1) {
    items[i].overlapPrefix = 0;
    items[i].overlapSuffix = 0;
  }
  for (let i = 0; i < items.length - 1; i += 1) {
    const ol = computeOverlapLen(items[i].text || "", items[i + 1].text || "");
    if (!ol) continue;
    items[i].overlapSuffix = ol;
    items[i + 1].overlapPrefix = ol;
  }
}

/** 连续普通块（leaf）之间也可能有 overlap（如固定长度切分） */
function annotateAdjacentLeafOverlaps(groups) {
  for (let i = 0; i < groups.length - 1; i += 1) {
    const a = groups[i];
    const b = groups[i + 1];
    if (a.type !== "leaf" || b.type !== "leaf") continue;
    const ol = computeOverlapLen(a.seg.text || "", b.seg.text || "");
    if (!ol) continue;
    a.seg.overlapSuffix = ol;
    b.seg.overlapPrefix = ol;
  }
}

/**
 * 把文本拆成「重叠 / 非重叠」片段，供黄底高亮。
 * @returns {{ text: string, isOverlap: boolean }[]}
 */
function overlapParts(seg) {
  const text = seg?.text || "";
  if (!text) return [];
  let prefix = Math.max(0, seg.overlapPrefix || 0);
  let suffix = Math.max(0, seg.overlapSuffix || 0);
  if (prefix + suffix > text.length) {
    // 整段都在重叠里时，优先标前缀，剩余标后缀
    prefix = Math.min(prefix, text.length);
    suffix = text.length - prefix;
  }
  const parts = [];
  if (prefix > 0) {
    parts.push({ text: text.slice(0, prefix), isOverlap: true });
  }
  const midEnd = text.length - suffix;
  if (midEnd > prefix) {
    parts.push({ text: text.slice(prefix, midEnd), isOverlap: false });
  }
  if (suffix > 0 && midEnd < text.length) {
    parts.push({ text: text.slice(midEnd), isOverlap: true });
  }
  return parts.length ? parts : [{ text, isOverlap: false }];
}

function parentSummary(text) {
  const raw = String(text || "").replace(/\s+/g, " ").trim();
  if (!raw) return "（空父块）";
  return raw.length > 120 ? `${raw.slice(0, 120)}…` : raw;
}

function isParentExpanded(gIdx) {
  return expandedParents.value.has(gIdx);
}

function toggleParent(gIdx) {
  const next = new Set(expandedParents.value);
  if (next.has(gIdx)) next.delete(gIdx);
  else next.add(gIdx);
  expandedParents.value = next;
}

function setParentBlockRef(gIdx, el) {
  if (el) parentBlockRefs.value[gIdx] = el;
  else delete parentBlockRefs.value[gIdx];
}

function scrollToFirstParent() {
  const idx = firstParentGroupIdx.value;
  if (idx < 0) {
    ElMessage.info("当前预览没有父块组，可将块大小调小后再预览");
    return;
  }
  const el = parentBlockRefs.value[idx];
  if (el?.scrollIntoView) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  flashParentIdx.value = idx;
  if (flashTimer) clearTimeout(flashTimer);
  flashTimer = setTimeout(() => {
    flashParentIdx.value = -1;
  }, 1600);
}

function fileLabel(file) {
  return file.docName || file.sourceUrl || `文件 #${file.id}`;
}

function buildPayload() {
  const payload = {
    docId: docId.value,
    splitType: form.splitType,
    chunkSize: form.chunkSize,
  };
  if (showOverlap.value) {
    payload.overlap = form.overlap ?? 0;
  }
  if (showTitleLevel.value) {
    payload.titleLevel = form.titleLevel;
  }
  if (showSeparator.value) {
    payload.separator = form.separator;
  }
  if (showRegex.value) {
    payload.regex = form.regex;
  }
  if (isCrawlSource.value && selectedFileId.value) {
    payload.fileId = selectedFileId.value;
  }
  return payload;
}

function applyStrategyDefaults(strategy) {
  if (!strategy?.paramSchema) return;
  const schema = strategy.paramSchema;
  const props = schema.properties || schema;
  if (props.chunkSize?.default != null) form.chunkSize = props.chunkSize.default;
  if (props.overlap?.default != null) form.overlap = props.overlap.default;
  if (props.titleLevel?.default != null) form.titleLevel = props.titleLevel.default;
  if (props.separator?.default != null) form.separator = props.separator.default;
  if (props.regex?.default != null) form.regex = props.regex.default;
}

function handleStrategyChange(code) {
  const strategy = strategies.value.find((s) => s.code === code);
  applyStrategyDefaults(strategy);
  strategyHelpActive.value = ["process"];
  previewResult.value = null;
  previewSegments.value = [];
  expandedParents.value = new Set();
  previewLoaded.value = false;
}

async function loadSourceText() {
  if (!docId.value) return;
  if (isCrawlSource.value && !selectedFileId.value) {
    sourceText.value = "";
    return;
  }
  sourceLoading.value = true;
  try {
    const params = isCrawlSource.value ? { fileId: selectedFileId.value } : {};
    const res = await previewDocument(docId.value, params);
    const text = typeof res === "string" ? res : res?.data ?? "";
    sourceText.value = typeof text === "string" ? text : String(text || "");
  } catch (e) {
    sourceText.value = "";
    ElMessage.warning(e?.msg || e?.message || "原文加载失败");
  } finally {
    sourceLoading.value = false;
  }
}

async function loadDocumentInfo() {
  if (!docId.value) return;
  try {
    const filesRes = await listDocumentFiles(docId.value);
    fileList.value = filesRes.data || [];
    if (isCrawlSource.value && fileList.value.length && !selectedFileId.value) {
      selectedFileId.value = fileList.value[0].id;
    }
  } catch {
    fileList.value = [];
  }

  try {
    if (isCrawlSource.value) {
      const res = await listCrawlerDocument({ pageNum: 1, pageSize: 200 });
      const rows = res.rows || res.data || [];
      const matched = rows.find((r) => Number(r.docId) === docId.value);
      if (matched) {
        docInfo.value = { docTitle: matched.docTitle };
      }
    } else {
      const res = await listDocumentRecord({ pageNum: 1, pageSize: 200 });
      const rows = res.rows || [];
      const matched = rows.find((r) => Number(r.docId) === docId.value);
      if (matched) {
        docInfo.value = { docTitle: matched.docTitle };
      }
    }
  } catch {
    /* 文档基础信息可选 */
  }

  await loadSourceText();
}

async function loadPageData() {
  if (!docId.value) {
    ElMessage.error("缺少文档 ID，无法进入配置页");
    router.back();
    return;
  }
  pageLoading.value = true;
  try {
    const [strategyRes, modelRes] = await Promise.all([
      getEmbeddingStrategies(),
      getEmbeddingModelInfo(),
    ]);
    strategies.value = strategyRes.data || [];
    modelInfo.value = modelRes.data || {};
    if (strategies.value.length && !strategies.value.some((s) => s.code === form.splitType)) {
      form.splitType = strategies.value[0].code;
    }
    applyStrategyDefaults(currentStrategy.value);
    if (form.chunkSize > chunkSizeMax.value) {
      form.chunkSize = chunkSizeMax.value;
    }
    await loadDocumentInfo();
  } catch (e) {
    ElMessage.error(e?.msg || e?.message || "加载配置数据失败");
  } finally {
    pageLoading.value = false;
  }
}

async function handlePreview() {
  if (!docId.value) return;
  if (isCrawlSource.value && !selectedFileId.value) {
    ElMessage.warning("请选择预览页面");
    return;
  }
  const valid = await paramRef.value?.validate().catch(() => false);
  if (!valid) return;

  previewLoading.value = true;
  previewLoaded.value = false;
  try {
    const res = await previewEmbedding(buildPayload());
    previewResult.value = res.data || {};
    previewSegments.value = previewResult.value.segments || [];
    expandedParents.value = new Set();
    flashParentIdx.value = -1;
    parentBlockRefs.value = {};
    previewLoaded.value = true;
    await nextTick();
    await nextTick();
    if (displayParentCount.value > 0) {
      scrollToFirstParent();
    }
  } catch (e) {
    ElMessage.error(e?.msg || e?.message || "预览失败");
  } finally {
    previewLoading.value = false;
  }
}

async function handleSubmit() {
  if (!docId.value) return;
  const valid = await paramRef.value?.validate().catch(() => false);
  if (!valid) return;

  submitLoading.value = true;
  try {
    const res = await createEmbeddingTask(buildPayload());
    const taskId = res.data?.taskId;
    ElMessage.success(`任务已创建，任务 ID：${taskId}`);
    try {
      await ElMessageBox.confirm(
        "是否前往 Embedding 任务列表查看进度？",
        "提交成功",
        {
          confirmButtonText: "查看任务",
          cancelButtonText: "留在此页",
          type: "success",
        }
      );
      router.push({ path: "/knowledge/embedding" });
    } catch {
      /* 用户选择留在此页 */
    }
  } catch (e) {
    const msg = e?.msg || e?.message || "提交失败";
    if (isExistingTaskError(msg)) {
      try {
        await ElMessageBox.confirm(
          `${msg}\n是否前往 Embedding 任务列表查看该文档相关任务？`,
          "任务已存在",
          {
            confirmButtonText: "查看任务",
            cancelButtonText: "留在此页",
            type: "warning",
          }
        );
        const query = { docId: String(docId.value) };
        if (docInfo.value?.docTitle) {
          query.docTitle = docInfo.value.docTitle;
        }
        router.push({ path: "/knowledge/embedding", query });
      } catch {
        /* 用户选择留在此页 */
      }
    } else {
      ElMessage.error(msg);
    }
  } finally {
    submitLoading.value = false;
  }
}

function isExistingTaskError(msg) {
  return typeof msg === "string" && msg.includes("该文档已有");
}

function handleCancel() {
  router.back();
}

watch(
  () => route.query.docId,
  () => {
    previewResult.value = null;
    previewSegments.value = [];
    expandedParents.value = new Set();
    previewLoaded.value = false;
    sourceText.value = "";
    loadPageData();
  }
);

watch(selectedFileId, () => {
  if (!isCrawlSource.value) return;
  previewResult.value = null;
  previewSegments.value = [];
  expandedParents.value = new Set();
  previewLoaded.value = false;
  loadSourceText();
});

onMounted(() => {
  loadPageData();
});
</script>

<style scoped>
.embedding-config {
  min-height: calc(100vh - 120px);
}
.config-main-row {
  align-items: flex-start;
}
.config-left {
  position: sticky;
  top: 12px;
  max-height: calc(100vh - 100px);
  overflow-y: auto;
  padding-right: 2px;
}
.config-right {
  position: sticky;
  top: 12px;
  max-height: calc(100vh - 100px);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.mb16 {
  margin-bottom: 16px;
}
.mt10 {
  margin-top: 10px;
}
.doc-meta-line {
  margin: -4px 0 16px;
  font-size: 13px;
  color: #909399;
  line-height: 1.6;
  word-break: break-all;
}
.doc-meta-line .meta-sep {
  margin: 0 8px;
  color: #dcdfe6;
}
.strategy-radio-group {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
}
.strategy-radio {
  margin-right: 0;
  height: auto;
  white-space: nowrap;
}
.strategy-help-card :deep(.el-card__body) {
  padding-top: 12px;
  padding-bottom: 8px;
}
.strategy-summary {
  margin: 0 0 8px;
  color: #606266;
  line-height: 1.6;
  font-size: 13px;
}
.strategy-help-collapse {
  border: none;
}
.strategy-help-collapse :deep(.el-collapse-item__header) {
  height: 36px;
  line-height: 36px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  border-bottom-color: #ebeef5;
}
.strategy-help-collapse :deep(.el-collapse-item__wrap) {
  border-bottom-color: #ebeef5;
}
.strategy-help-collapse :deep(.el-collapse-item__content) {
  padding-bottom: 12px;
}
.strategy-help-collapse :deep(.el-collapse-item:last-child .el-collapse-item__header),
.strategy-help-collapse :deep(.el-collapse-item:last-child .el-collapse-item__wrap) {
  border-bottom: none;
}
.param-hint {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.5;
  color: #909399;
}
.regex-template-select {
  margin-bottom: 8px;
}
.regex-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}
.regex-option-label {
  flex-shrink: 0;
}
.regex-option-pattern {
  font-size: 12px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
.strategy-list {
  margin: 0;
  padding-left: 18px;
  color: #606266;
  line-height: 1.7;
  font-size: 13px;
}
.strategy-process {
  list-style: decimal;
}
.strategy-process li + li {
  margin-top: 4px;
}
.strategy-scene-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.file-option-label {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preview-tip {
  margin-bottom: 12px;
  flex-shrink: 0;
}
.preview-tip-sub {
  margin-top: 4px;
  font-size: 12px;
  font-weight: 400;
  color: #909399;
}
.preview-meta {
  margin-top: 12px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  flex-shrink: 0;
}
.preview-meta-text {
  font-size: 13px;
  color: #909399;
}
.compare-preview {
  margin-top: 12px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  flex: 1;
  min-height: 360px;
}
.source-only-wrap {
  margin-top: 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fafafa;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 360px;
}
.source-only-wrap .source-only {
  flex: 1;
  min-height: 0;
  max-height: none;
}
.compare-pane {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fafafa;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
.compare-pane-title {
  flex-shrink: 0;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  background: #f5f7fa;
  border-bottom: 1px solid #ebeef5;
}
.article-preview {
  flex: 1;
  min-height: 0;
  max-height: none;
  overflow: auto;
  padding: 12px 14px;
  background: #fff;
  font-size: 14px;
  line-height: 1.85;
  word-break: break-word;
  white-space: pre-wrap;
  font-family: "SF Mono", "Menlo", "Consolas", "PingFang SC", "Microsoft YaHei", monospace;
}
.chunk-list-preview {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.chunk-block {
  white-space: pre-wrap;
  padding: 10px 12px;
  border: 1px solid #c0c4cc;
  border-radius: 6px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}
.chunk-block.is-child {
  background: #fff;
  border: 1px solid #f5c26b;
  box-shadow: inset 3px 0 0 #e6a23c;
}
.chunk-block .chunk-mark {
  display: inline-block;
  margin: 0 6px 6px 0;
  padding: 0 5px;
  font-size: 11px;
  line-height: 1.5;
  border: 1px solid currentColor;
  border-radius: 3px;
  background: #fff;
  vertical-align: middle;
  user-select: none;
}
.chunk-block .chunk-text {
  white-space: pre-wrap;
}
.chunk-block .chunk-text .is-overlap {
  background: rgba(250, 204, 21, 0.55);
  border-radius: 2px;
  box-shadow: inset 0 -1px 0 rgba(234, 179, 8, 0.65);
}
.parent-block {
  border: 2px solid #e6a23c;
  border-radius: 8px;
  background: #fff8e6;
  padding: 12px;
  box-shadow: 0 0 0 1px rgba(230, 162, 60, 0.15);
}
.parent-block.is-flash {
  animation: parent-flash 1.4s ease;
}
@keyframes parent-flash {
  0%,
  100% {
    box-shadow: 0 0 0 1px rgba(230, 162, 60, 0.15);
  }
  30%,
  60% {
    box-shadow: 0 0 0 4px rgba(230, 162, 60, 0.45);
  }
}
.parent-block-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.parent-meta {
  font-size: 12px;
  color: #b88230;
}
.parent-block-summary {
  white-space: pre-wrap;
  padding: 8px 10px;
  margin-bottom: 10px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.75);
  color: #909399;
  font-size: 12px;
  line-height: 1.6;
  border: 1px dashed #f0c78a;
}
.parent-block-body {
  white-space: pre-wrap;
  padding: 8px 10px;
  margin-bottom: 10px;
  border-radius: 4px;
  background: #fff;
  color: #909399;
  font-size: 13px;
  max-height: 220px;
  overflow: auto;
  border: 1px dashed #dcdfe6;
}
.parent-block-body.is-always {
  max-height: none;
  color: #606266;
}
.child-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 4px;
  padding: 10px 10px 10px 12px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.65);
  border-left: 4px solid #e6a23c;
}
.role-tag {
  display: inline-block;
  padding: 0 8px;
  font-size: 12px;
  line-height: 1.7;
  border-radius: 3px;
  font-weight: 700;
}
.role-tag.is-parent {
  color: #fff;
  background: #e6a23c;
}
.role-tag.is-child-tag {
  margin: 0 6px 6px 0;
  color: #06723a;
  background: #e1f3d8;
}
.source-preview {
  color: #606266;
}
.source-continuous .source-part.is-chunk {
  border-radius: 2px;
}
.footer-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-start;
  gap: 12px;
  margin-bottom: 12px;
  padding: 0 0 12px;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 5;
  background: var(--el-bg-color, #fff);
}
.preview-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.preview-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
</style>

<!-- teleported 下拉挂到 body，需非 scoped 才能约束宽度 -->
<style>
.embedding-file-select-popper.el-select__popper,
.embedding-file-select-popper {
  max-width: 280px;
}
.embedding-file-select-popper .el-select-dropdown__item {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
