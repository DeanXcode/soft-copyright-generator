import React from "react";
import { CheckCircle2, ChevronDown, FileCheck2 } from "lucide-react";

export default function ResultReport({ result, qualityItems, generatedFiles, bridgeAvailable, onOpenFile, getDeliveryStatus, renderQualityIcon }) {
  return (
    <div className="result-report">
      <div className="result-hero">
        <span className="result-hero-icon"><CheckCircle2 size={30} /></span>
        <div>
          <small>DELIVERY READY</small>
          <strong>软著材料包已准备完成</strong>
          <p>说明书、源码鉴别材料、申请信息与校验报告已完成汇总。</p>
        </div>
        <em>{generatedFiles.length || 0} 个文件</em>
      </div>
      <div className="report-paths">
        <div>
          <small>输出目录</small>
          <b>{result.outputDir || "未返回"}</b>
        </div>
        <div>
          <small>材料包</small>
          <b>{result.zipPath || "未返回"}</b>
        </div>
      </div>
      <DeliveryStatus result={result} getDeliveryStatus={getDeliveryStatus} renderQualityIcon={renderQualityIcon} />
      <div className="quality-grid">
        {qualityItems.slice(0, 6).map((item) => (
          <div className={`quality-item ${item.state}`} key={item.label}>
            <span>{renderQualityIcon(item.state)}</span>
            <div>
              <strong>{item.label}</strong>
              <p>{item.value}</p>
              {item.detail && <small>{item.detail}</small>}
            </div>
          </div>
        ))}
      </div>
      <details className="report-details">
        <summary>
          <FileCheck2 size={16} />
          <span>文件与校验详情</span>
          <ChevronDown size={16} />
        </summary>
        <div className="file-list">
          {generatedFiles.length ? (
            generatedFiles.slice(0, 12).map((file) => (
              <button
                className="file-row"
                key={file.path || file.name}
                type="button"
                title={bridgeAvailable ? file.path : "Electron 中可打开文件"}
                disabled={!bridgeAvailable}
                onClick={() => onOpenFile(file)}
              >
                {file.icon}
                <span>{file.name}</span>
              </button>
            ))
          ) : (
            <p>本次未返回文件列表。</p>
          )}
        </div>
      </details>
    </div>
  );
}
function DeliveryStatus({ result, getDeliveryStatus, renderQualityIcon }) {
  const status = getDeliveryStatus(result);
  return (
    <div className={`delivery-status ${status.state}`}>
      <span className="quality-state">{renderQualityIcon(status.state)}</span>
      <div>
        <strong>{status.title}</strong>
        <p>{status.detail}</p>
      </div>
    </div>
  );
}
