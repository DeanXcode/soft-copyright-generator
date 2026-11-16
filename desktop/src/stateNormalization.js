const DEFAULT_STATUSES = new Set(["queued", "planning", "running", "success", "error", "cancelled"]);

export function normalizeStringList(value, limit = 20) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.map((item) => String(item ?? "").trim()).filter(Boolean))].slice(0, limit);
}

export function normalizeBusinessPlanState(value) {
  const source = value && typeof value === "object" ? value : {};
  const modules = Array.isArray(source.modules)
    ? source.modules.map((module, index) => normalizeBusinessModule(module, index)).filter(Boolean).slice(0, 20)
    : [];
  return {
    softwareName: String(source.softwareName ?? source.name ?? "").trim(),
    productType: String(source.productType ?? "").trim(),
    domain: String(source.domain ?? "").trim(),
    profile: String(source.profile ?? "").trim(),
    targetUsers: normalizeStringList(source.targetUsers, 8),
    avoidTerms: normalizeStringList(source.avoidTerms, 12),
    modules
  };
}

function normalizeBusinessModule(value, index) {
  if (!value || typeof value !== "object") return null;
  const title = String(value.title ?? value.name ?? "").trim();
  const description = String(value.description ?? value.focus ?? "").trim();
  if (!title && !description) return null;
  const children = Array.isArray(value.children)
    ? value.children
        .map((child, childIndex) => {
          if (!child || typeof child !== "object") return null;
          return {
            ...child,
            id: String(child.id ?? `child_${index + 1}_${childIndex + 1}`),
            title: String(child.title ?? child.name ?? "新增细分功能").trim() || "新增细分功能"
          };
        })
        .filter(Boolean)
        .slice(0, 20)
    : [];
  return {
    ...value,
    id: String(value.id ?? `module_${index + 1}`),
    category: String(value.category ?? "业务模块").trim() || "业务模块",
    title: title || `业务模块 ${index + 1}`,
    description: description || "请补充该模块面向的业务对象、处理流程和关键结果。",
    dataObjects: normalizeStringList(value.dataObjects, 10),
    userFlow: normalizeStringList(value.userFlow, 10),
    screens: normalizeStringList(value.screens, 10),
    operations: normalizeStringList(value.operations, 12),
    dataFields: normalizeStringList(value.dataFields, 12),
    rules: normalizeStringList(value.rules, 10),
    entities: normalizeStringList(value.entities, 10),
    operationSpecs: Array.isArray(value.operationSpecs) ? value.operationSpecs.filter((item) => item && typeof item === "object").slice(0, 12) : [],
    children
  };
}

export function normalizeQueueTask(value, index = 0) {
  if (!value || typeof value !== "object") return null;
  const status = DEFAULT_STATUSES.has(value.status) ? value.status : "queued";
  const businessPlan = value.businessPlan ? normalizeBusinessPlanState(value.businessPlan) : null;
  return {
    ...value,
    id: String(value.id ?? `queue_restored_${index + 1}`),
    title: String(value.title ?? value.formSnapshot?.name ?? value.businessPlan?.softwareName ?? "恢复任务").trim() || "恢复任务",
    promptText: String(value.promptText ?? value.title ?? ""),
    status,
    phase: String(value.phase ?? "queued"),
    progress: Number.isFinite(Number(value.progress)) ? Math.max(0, Math.min(100, Number(value.progress))) : 0,
    events: Array.isArray(value.events) ? value.events.filter((event) => event && typeof event === "object").slice(-80) : [],
    businessPlan,
    autoPlan: Boolean(value.autoPlan || !businessPlan?.modules.length),
    restoredFromRunning: Boolean(value.restoredFromRunning),
    formSnapshot: value.formSnapshot && typeof value.formSnapshot === "object" ? { ...value.formSnapshot } : {},
    result: value.result && typeof value.result === "object" ? value.result : null
  };
}

export function normalizeQueueState(value) {
  const source = value && typeof value === "object" ? value : {};
  const tasks = Array.isArray(source.tasks) ? source.tasks.map(normalizeQueueTask).filter(Boolean) : [];
  return {
    tasks: dedupeQueueTasksByOutputDir(tasks).slice(-30),
    paused: Boolean(source.paused)
  };
}

function normalizedQueueOutputDir(value) {
  return String(value ?? "")
    .trim()
    .replace(/[\\/]+$/, "")
    .replace(/\\/g, "/")
    .toLowerCase();
}

export function queueTaskOutputDir(task) {
  return normalizedQueueOutputDir(
    task?.recovery?.outputDir ||
      task?.result?.outputDir ||
      task?.overrides?.resumeOutputDir ||
      ""
  );
}

export function dedupeQueueTasksByOutputDir(tasks) {
  const current = Array.isArray(tasks) ? tasks : [];
  const seen = new Set();
  const result = [];
  for (let index = current.length - 1; index >= 0; index -= 1) {
    const task = current[index];
    const outputDir = queueTaskOutputDir(task);
    if (outputDir && seen.has(outputDir)) continue;
    if (outputDir) seen.add(outputDir);
    result.unshift(task);
  }
  return result;
}

export function enqueueOrReplaceRetryTask(tasks, newTask, options = {}) {
  const current = Array.isArray(tasks) ? tasks : [];
  if (!options.retry) return [...current, newTask];
  const outputDir = queueTaskOutputDir(newTask);
  if (!outputDir) return [...current, newTask];

  const matchingIndexes = current
    .map((task, index) => (queueTaskOutputDir(task) === outputDir ? index : -1))
    .filter((index) => index >= 0);
  if (!matchingIndexes.length) return [...current, newTask];
  if (matchingIndexes.some((index) => ["planning", "running"].includes(current[index]?.status))) {
    return current;
  }

  const replacementIndex = matchingIndexes[0];
  const previous = current[replacementIndex] || {};
  const replacement = {
    ...newTask,
    id: previous.id || newTask.id,
    createdAt: previous.createdAt || newTask.createdAt
  };
  return current.flatMap((task, index) => {
    if (queueTaskOutputDir(task) !== outputDir) return [task];
    return index === replacementIndex ? [replacement] : [];
  });
}

export function normalizeModelCatalogState(value) {
  const source = value && typeof value === "object" ? value : {};
  return {
    status: String(source.status ?? "idle"),
    provider: String(source.provider ?? ""),
    models: Array.isArray(source.models) ? source.models.map((model) => String(model ?? "").trim()).filter(Boolean).slice(0, 200) : [],
    message: String(source.message ?? "")
  };
}
