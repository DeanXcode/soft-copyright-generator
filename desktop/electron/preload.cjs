const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("softCopyright", {
  generateMaterials: (payload) => ipcRenderer.invoke("generate-materials", payload),
  cancelGeneration: () => ipcRenderer.invoke("cancel-generation"),
  getGenerationStatus: () => ipcRenderer.invoke("get-generation-status"),
  inferFeatureHint: (payload) => ipcRenderer.invoke("infer-feature-hint", payload),
  getModelConfig: () => ipcRenderer.invoke("get-model-config"),
  listAvailableModels: () => ipcRenderer.invoke("list-available-models"),
  saveModelConfig: (payload) => ipcRenderer.invoke("save-model-config", payload),
  getModelAccount: () => ipcRenderer.invoke("get-model-account"),
  listRecoverableTasks: () => ipcRenderer.invoke("list-recoverable-tasks"),
  deleteRecoverableTask: (payload) => ipcRenderer.invoke("delete-recoverable-task", payload),
  openPath: (targetPath) => ipcRenderer.invoke("open-path", targetPath),
  onGenerateEvent: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("generate-event", listener);
    return () => ipcRenderer.removeListener("generate-event", listener);
  }
});
