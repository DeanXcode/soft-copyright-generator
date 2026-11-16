import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const allowlistPath = path.join(root, "scripts", "npm-audit-allowlist.json");
const allowlist = JSON.parse(fs.readFileSync(allowlistPath, "utf8"));
const allowed = new Map((allowlist.entries || []).map((entry) => [String(entry.id), entry]));
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
const result = spawnSync(
  npmCommand,
  ["audit", "--json", "--registry=https://registry.npmjs.org"],
  { cwd: root, encoding: "utf8", windowsHide: true }
);

let report;
try {
  report = JSON.parse(result.stdout || "{}");
} catch (error) {
  throw new Error(`Unable to parse npm audit output: ${error.message}\n${result.stderr || result.stdout}`);
}

if (report.error) {
  throw new Error(`npm audit failed: ${report.error.summary || report.error.detail || JSON.stringify(report.error)}`);
}

const vulnerabilities = report.vulnerabilities || {};
const advisoryRoots = (packageName, visited = new Set()) => {
  if (visited.has(packageName)) return [];
  visited.add(packageName);
  const item = vulnerabilities[packageName];
  if (!item || !Array.isArray(item.via)) return [];
  const roots = [];
  for (const via of item.via) {
    if (via && typeof via === "object") {
      const id = String(via.url || via.source || packageName).split("/").filter(Boolean).at(-1);
      roots.push({ id, packageName, severity: String(via.severity || item.severity || "") });
    } else if (typeof via === "string") {
      roots.push(...advisoryRoots(via, new Set(visited)));
    }
  }
  return roots;
};

const today = new Date().toISOString().slice(0, 10);
const blocking = [];
const acknowledged = [];
for (const [packageName, item] of Object.entries(vulnerabilities)) {
  if (!new Set(["high", "critical"]).has(String(item.severity || "").toLowerCase())) continue;
  const roots = advisoryRoots(packageName);
  if (!roots.length) {
    blocking.push(`${packageName}: ${item.severity} (no root advisory found)`);
    continue;
  }
  for (const advisory of roots) {
    const exception = allowed.get(advisory.id);
    if (!exception || !exception.reason || !exception.expires || exception.expires < today) {
      blocking.push(`${packageName}: ${advisory.id} (${advisory.severity || item.severity})`);
    } else {
      acknowledged.push(`${advisory.id} until ${exception.expires}: ${exception.reason}`);
    }
  }
}

if (blocking.length) {
  throw new Error(`Unapproved high/critical npm vulnerabilities:\n- ${[...new Set(blocking)].join("\n- ")}`);
}

for (const line of [...new Set(acknowledged)]) console.log(`audit exception: ${line}`);
const counts = report.metadata?.vulnerabilities || {};
console.log(`npm audit accepted: critical=${counts.critical || 0}, high=${counts.high || 0}, low=${counts.low || 0}`);
