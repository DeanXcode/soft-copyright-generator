import React from "react";
import { FolderOpen, ListOrdered, RefreshCw, Square, Trash2 } from "lucide-react";

export default function QueuePanel({
  taskQueue,
  activeQueueTaskId,
  queuePaused,
  queueSummary,
  recoverableTasks,
  recoveryStatus,
  bridgeAvailable,
  onToggleQueuePaused,
  onRemoveQueueTask,
  onRetryQueueTask,
  onOpenQueueTaskOutput,
  onRestoreRecoverableTask,
  onDeleteRecoverableTask
}) {
  const safeTasks = Array.isArray(taskQueue) ? taskQueue.filter((task) => task && typeof task === "object") : [];
  const safeSummary = queueSummary && typeof queueSummary === "object"
    ? queueSummary
    : { total: safeTasks.length, queued: 0, running: 0, success: 0, error: 0, cancelled: 0 };
  const visibleTasks = safeTasks.slice(-8);
  const hasTasks = safeTasks.length > 0;
  const runningTask = safeTasks.find((task) => task.status === "running" || task.status === "planning");
  const canToggleQueue = hasTasks && safeSummary.queued > 0;
  const recoverableVisible = Array.isArray(recoverableTasks) ? recoverableTasks.filter(Boolean).slice(0, 3) : [];
  const summaryText = hasTasks
    ? `${safeSummary.total} 项 · ${safeSummary.queued} 等待 · ${safeSummary.running} 运行 · ${safeSummary.success} 完成`
    : "可在底部输入框追加任务，队列会按顺序一个一个生成";
  return (
    <section className="work-section queue-section">
      <div className="queue-compact-head">
        <div className="queue-title-group">
          <span className="queue-brand-mark"><ListOrdered size={18} /></span>
          <div>
            <strong>顺序队列</strong>
            <span>{queuePaused ? "已暂停后续任务" : runningTask ? `正在处理：${runningTask.title}` : summaryText}</span>
          </div>
        </div>
        <button type="button" onClick={onToggleQueuePaused} disabled={!canToggleQueue}>
          {queuePaused ? <RefreshCw size={15} /> : <Square size={15} />}
          <span>{queuePaused ? "继续队列" : "暂停后续"}</span>
        </button>
      </div>
      {recoverableVisible.length > 0 && (
        <div className="queue-recovery-strip">
          <span className="queue-recovery-label">{recoveryStatus || "发现上次未完成任务"}</span>
          {recoverableVisible.map((task) => (
            <span className="queue-recovery-item" key={task.id || task.outputDir || task.title}>
              <button type="button" className="queue-recovery-action" onClick={() => onRestoreRecoverableTask(task)} title={`恢复 ${task.title || "任务"}`}>
                <RefreshCw size={15} />
                <span>
                  恢复 {task.title}
                  {task.pageEngineUpgradeRequired && <small>页面生成引擎已升级，将复用蓝图和参考图并重新生成全部界面</small>}
                  {task.domainProfile?.key && <small>领域：{domainProfileLabel(task.domainProfile.key)}{task.domainProfile.gateReasons ? ` · ${task.domainProfile.gateReasons}` : ""}</small>}
                </span>
              </button>
              <button
                type="button"
                className="queue-recovery-delete"
                onClick={() => onDeleteRecoverableTask(task)}
                aria-label={`删除恢复记录 ${task.title || ""}`}
                title="删除恢复记录"
              >
                <Trash2 size={14} />
              </button>
            </span>
          ))}
        </div>
      )}
      {hasTasks && (
        <div className="queue-list">
          {visibleTasks.map((task) => {
            const active = task.id === activeQueueTaskId;
            const latestEvent = task.events?.length ? task.events[task.events.length - 1] : null;
            const canRetry = task.status === "error" || task.status === "cancelled";
            const canRemove = task.status !== "running" && task.status !== "planning";
            return (
              <div className={`queue-row ${task.status} ${active ? "active" : ""}`} key={task.id}>
                <span className="queue-status-dot" />
                <div className="queue-row-main">
                  <p>
                    <strong>{task.title}</strong>
                    <em>{queueTaskStatusLabel(task)}</em>
                  </p>
                  <small>{latestEvent?.message || queueTaskMeta(task)}</small>
                  <div className="queue-row-progress">
                    <span style={{ width: `${Math.min(100, task.progress || 0)}%` }} />
                  </div>
                </div>
                <div className="queue-row-actions">
                  {task.result?.ok && (
                    <button
                      type="button"
                      title="打开输出目录"
                      disabled={!bridgeAvailable || !task.result?.outputDir}
                      onClick={() => onOpenQueueTaskOutput(task.id, "output")}
                    >
                      <FolderOpen size={15} />
                    </button>
                  )}
                  {canRetry && (
                    <button
                      type="button"
                      title={task.recovery?.outputDir || task.result?.outputDir ? "保留蓝图并从失败阶段续跑" : "重试该任务"}
                      onClick={() => onRetryQueueTask(task.id)}
                    >
                      <RefreshCw size={15} />
                    </button>
                  )}
                  <button type="button" title="移除任务" disabled={!canRemove} onClick={() => onRemoveQueueTask(task.id)}>
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            );
          })}
          {safeTasks.length > visibleTasks.length && <small className="queue-more">仅显示最近 {visibleTasks.length} 项，共 {safeTasks.length} 项</small>}
        </div>
      )}
    </section>
  );
}

function domainProfileLabel(key) {
  const labels = {
    transport_route: "交通线路",
    download_manager: "下载管理",
    workforce_attendance: "考勤人力",
    medical: "医疗",
    survey_mapping: "测绘地理",
    smart_manufacturing: "智能制造",
    rail_construction_quality: "轨道施工质量",
    general_business: "通用业务"
  };
  return labels[key] || key;
}

function queueTaskStatusLabel(task) {
  if (task.status === "queued") return "等待中";
  if (task.status === "planning") return "生成蓝图";
  if (task.status === "running") return "生成材料";
  if (task.status === "success") return "已完成";
  if (task.status === "error") return "失败";
  if (task.status === "cancelled") return "已中止";
  return "待处理";
}

function queueTaskMeta(task) {
  if (task.recovery?.outputDir && task.status === "queued") return "从上次失败输出恢复，等待继续生成";
  if (task.status === "queued") return task.autoPlan ? "等待自动生成蓝图后进入材料生成" : "等待使用已确认蓝图生成";
  if (task.status === "success") return task.result?.zipPath ? "材料包已生成，可打开输出目录" : "任务已完成";
  if (task.status === "error") return task.result?.stderr || "任务失败，队列已暂停";
  if (task.status === "cancelled") return "任务已中止，队列已暂停";
  if (task.phase === "outline") return "正在生成产品蓝图";
  if (task.phase === "materials") return "正在生成源码、截图、手册和材料包";
  return "正在处理";
}
