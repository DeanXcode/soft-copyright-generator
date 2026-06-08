const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("softCopyright", {
  generateMaterials: (payload) => ipcRenderer.invoke("generate-materials", payload),
  getModelConfig: () => ipcRenderer.invoke("get-model-config"),
  saveModelConfig: (payload) => ipcRenderer.invoke("save-model-config", payload),
  getModelAccount: () => ipcRenderer.invoke("get-model-account"),
  openPath: (targetPath) => ipcRenderer.invoke("open-path", targetPath),
  onGenerateEvent: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("generate-event", listener);
    return () => ipcRenderer.removeListener("generate-event", listener);
  }
});
