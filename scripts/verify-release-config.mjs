import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const readJson = (filePath) => JSON.parse(fs.readFileSync(filePath, "utf8").replace(/^\uFEFF/, ""));
const packageJson = readJson(path.join(root, "package.json"));
const packageLock = readJson(path.join(root, "package-lock.json"));
const exampleConfig = readJson(path.join(root, "config", "production.example.json"));

if (packageJson.version !== packageLock.version || packageJson.version !== packageLock.packages?.[""]?.version) {
  throw new Error("package.json and package-lock.json versions are inconsistent");
}
if (!packageJson.build?.extraResources?.some((item) => item?.from === "requirements-lock.txt")) {
  throw new Error("requirements-lock.txt is not included in packaged resources");
}
const exampleKey = String(exampleConfig.SOFT_MODEL_GPT_API_KEY || "");
if (!exampleKey.includes("your-") && !exampleKey.includes("placeholder")) {
  throw new Error("production.example.json must contain only an explicit placeholder API key");
}

const tracked = execFileSync("git", ["ls-files", "-z"], { cwd: root, encoding: "utf8", windowsHide: true })
  .split("\0")
  .filter(Boolean);
const secretPatterns = [
  /sk-[A-Za-z0-9_-]{20,}/g,
  /xai-[A-Za-z0-9_-]{20,}/g,
  /AIza[0-9A-Za-z_-]{24,}/g
];
const allowedFiles = new Set(["config/production.example.json", "README.md"]);
const leaks = [];
for (const relative of tracked) {
  if (allowedFiles.has(relative.replaceAll("\\", "/"))) continue;
  const absolute = path.join(root, relative);
  let source;
  try {
    source = fs.readFileSync(absolute, "utf8");
  } catch {
    continue;
  }
  for (const pattern of secretPatterns) {
    if (pattern.test(source)) leaks.push(relative);
    pattern.lastIndex = 0;
  }
}
if (leaks.length) throw new Error(`Possible tracked API secrets found in: ${[...new Set(leaks)].join(", ")}`);

console.log(`release config verified for version ${packageJson.version}`);
