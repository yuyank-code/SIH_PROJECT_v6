const fs = require("fs");
const path = require("path");
const parser = require("@babel/parser");

const ROOT = path.resolve(__dirname, "..");
const SRC = path.join(ROOT, "src");
const EXTENSIONS = new Set([".js", ".jsx"]);

function walk(dir, files = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (["node_modules", "build", ".git"].includes(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, files);
    else if (EXTENSIONS.has(path.extname(entry.name))) files.push(full);
  }
  return files;
}

const files = walk(SRC);
const errors = [];

for (const file of files) {
  const code = fs.readFileSync(file, "utf8");
  try {
    parser.parse(code, {
      sourceType: "module",
      sourceFilename: path.relative(ROOT, file),
      plugins: ["jsx", "optionalChaining", "nullishCoalescingOperator", "classProperties", "objectRestSpread", "dynamicImport"],
    });
  } catch (error) {
    errors.push({ file: path.relative(ROOT, file), message: error.message });
  }
}

if (errors.length) {
  console.error("Frontend syntax validation failed:");
  for (const error of errors) console.error(`- ${error.file}: ${error.message}`);
  process.exit(1);
}

console.log(`Frontend syntax validation passed for ${files.length} JS/JSX files.`);
