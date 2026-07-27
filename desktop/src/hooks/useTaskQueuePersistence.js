import { useEffect, useRef, useState } from "react";

export default function useTaskQueuePersistence(loadState, persistState) {
  const initialState = useRef(null);
  if (!initialState.current) initialState.current = loadState();

  const [taskQueue, setTaskQueue] = useState(initialState.current.tasks || []);
  const [queuePaused, setQueuePaused] = useState(Boolean(initialState.current.paused));
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
