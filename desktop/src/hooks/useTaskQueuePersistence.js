import { useEffect, useRef, useState } from "react";
import { dedupeQueueTasksByOutputDir, normalizeQueueState, normalizeQueueTask } from "../stateNormalization";

export default function useTaskQueuePersistence(loadState, persistState) {
  const initialState = useRef(null);
  if (!initialState.current) initialState.current = normalizeQueueState(loadState());

  const [taskQueueState, setTaskQueueState] = useState(initialState.current.tasks);
  const [queuePaused, setQueuePaused] = useState(Boolean(initialState.current.paused));
  const taskQueue = Array.isArray(taskQueueState) ? taskQueueState : [];
  const setTaskQueue = (nextValue) => {
    setTaskQueueState((current) => {
      const currentTasks = Array.isArray(current) ? current : [];
      const next = typeof nextValue === "function" ? nextValue(currentTasks) : nextValue;
      const normalized = (Array.isArray(next) ? next : []).map(normalizeQueueTask).filter(Boolean);
      return dedupeQueueTasksByOutputDir(normalized).slice(-30);
    });
  };
  const taskQueueRef = useRef(taskQueue);

  useEffect(() => {
    taskQueueRef.current = taskQueue;
  }, [taskQueue]);

  useEffect(() => {
    persistState(taskQueue, queuePaused);
  }, [persistState, queuePaused, taskQueue]);

  return {
    taskQueue,
    setTaskQueue,
    queuePaused,
    setQueuePaused,
    taskQueueRef
  };
}
