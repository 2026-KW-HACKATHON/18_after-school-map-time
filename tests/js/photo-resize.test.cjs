// 사진 줄이기: 크기 계산, 줄일지 말지 판단, 사진 칸 바꾸기·제출 대기·10MB 안내 (node --test tests/js/photo-resize.test.cjs)
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(`${__dirname}/../../static/js/photo-resize.js`, "utf8");

const MB = 1024 * 1024;

function load(extra = {}) {
  const context = { module: { exports: {} }, File, Blob, Promise, Set, Map, ...extra };
  vm.runInNewContext(source, context);
  return context.module.exports;
}

const fakeFile = (size, name = "IMG_0001.JPG", type = "image/jpeg") =>
  ({ size, name, type, lastModified: 1 });
const blobOf = (size) => new Blob([new Uint8Array(size)], { type: "image/jpeg" });
const deps = (width, height, outSize) => ({
  decode: async () => ({ image: {}, width, height, release() { this.released = true; } }),
  encode: async (image, w, h) => { deps.last = [w, h]; return blobOf(outSize); },
});

test("긴 변을 1600px로 맞추고 작은 사진은 키우지 않는다", () => {
  const { targetSize } = load();
  assert.deepEqual({ ...targetSize(4032, 3024) }, { width: 1600, height: 1200 });
  assert.deepEqual({ ...targetSize(3024, 4032) }, { width: 1200, height: 1600 });
  assert.deepEqual({ ...targetSize(800, 600) }, { width: 800, height: 600 });
  assert.deepEqual({ ...targetSize(10000, 1) }, { width: 1600, height: 1 });
});

test("파일 이름은 .jpg로 바뀐다", () => {
  const { jpegName } = load();
  assert.equal(jpegName("IMG_0001.HEIC"), "IMG_0001.jpg");
  assert.equal(jpegName("door.photo.png"), "door.photo.jpg");
  assert.equal(jpegName("noext"), "noext.jpg");
  assert.equal(jpegName(""), "photo.jpg");
});

test("큰 폰 사진은 줄인 JPEG로 바뀐다", async () => {
  const { shrink } = load();
  const d = deps(4032, 3024, 800 * 1024);
  const result = await shrink(fakeFile(6 * MB), d);
  assert.equal(result.resized, true);
  assert.equal(result.file.name, "IMG_0001.jpg");
  assert.equal(result.file.type, "image/jpeg");
  assert.equal(result.file.size, 800 * 1024);
  assert.deepEqual(deps.last, [1600, 1200]);
});

test("작은 사진·사진 아닌 파일·못 여는 사진·줄여도 커지는 사진은 원본 그대로", async () => {
  const { shrink } = load();
  const small = fakeFile(300 * 1024);
  assert.equal((await shrink(small, deps(4000, 3000, 1))).file, small);
  const pdf = fakeFile(5 * MB, "a.pdf", "application/pdf");
  assert.equal((await shrink(pdf, deps(4000, 3000, 1))).file, pdf);
  const heic = fakeFile(3 * MB, "IMG_0002.HEIC", "");
  const failing = { decode: async () => { throw new Error("지원 안 함"); }, encode: async () => blobOf(1) };
  const kept = await shrink(heic, failing);
  assert.equal(kept.file, heic);
  assert.equal(kept.resized, false);
  const already = fakeFile(1 * MB);
  assert.equal((await shrink(already, deps(1200, 900, 2 * MB))).resized, false);
});

test("열었던 사진은 줄인 뒤 정리한다", async () => {
  const { shrink } = load();
  let released = false;
  const d = { decode: async () => ({ image: {}, width: 4000, height: 3000, release: () => { released = true; } }),
              encode: async () => blobOf(10) };
  await shrink(fakeFile(2 * MB), d);
  assert.equal(released, true);
});

// 사진 칸이 있는 폼 흉내
function page({ fileSize, outSize, dataTransfer = true }) {
  const listeners = {};
  const doc = { addEventListener: (name, fn) => { listeners[name] = fn; },
                createElement: () => ({ classList: { contains: (c) => c === "photo-resize-status" },
                                        setAttribute() {}, textContent: "" }) };
  const form = { submitted: [], requestSubmit(by) { this.submitted.push(by); } };
  const input = { type: "file", files: [fakeFile(fileSize)], validity: "",
                  setCustomValidity(msg) { this.validity = msg; },
                  closest: () => form, nextElementSibling: null,
                  insertAdjacentElement(_, el) { this.nextElementSibling = el; } };
  form.input = input;
  class FakeTransfer { constructor() { const files = []; this.files = files; this.items = { add: (f) => files.push(f) }; } }
  const api = load(dataTransfer ? { DataTransfer: FakeTransfer } : {});
  const d = deps(4032, 3024, outSize);
  api.init(doc, d);
  return { listeners, form, input };
}
const flush = () => new Promise((resolve) => setImmediate(resolve));

test("사진을 고르면 줄인 파일로 칸이 바뀌고 안내가 나온다", async () => {
  const { listeners, input } = page({ fileSize: 6 * MB, outSize: 700 * 1024 });
  listeners.change({ target: input });
  assert.match(input.nextElementSibling.textContent, /줄이는 중/);
  await flush();
  assert.equal(input.files[0].name, "IMG_0001.jpg");
  assert.equal(input.files[0].size, 700 * 1024);
  assert.equal(input.nextElementSibling.textContent, "사진을 줄였어요 (6.0MB → 0.7MB)");
  assert.equal(input.validity, "");
});

test("줄이는 중에 제출하면 기다렸다가 같은 버튼으로 다시 제출한다", async () => {
  const { listeners, form, input } = page({ fileSize: 6 * MB, outSize: 700 * 1024 });
  listeners.change({ target: input });
  let prevented = false;
  const button = { name: "save" };
  listeners.submit({ target: form, submitter: button, preventDefault: () => { prevented = true; } });
  assert.equal(prevented, true);
  assert.deepEqual(form.submitted, []);
  await flush();
  assert.deepEqual(form.submitted, [button]);
  assert.equal(form.input.files[0].name, "IMG_0001.jpg");

  // 줄이기가 끝난 뒤의 제출은 그대로 통과
  prevented = false;
  listeners.submit({ target: form, preventDefault: () => { prevented = true; } });
  assert.equal(prevented, false);
});

test("줄일 수 없는 10MB 넘는 사진은 제출 전에 막고 안내한다", async () => {
  const { listeners, input } = page({ fileSize: 12 * MB, outSize: 20 * MB, dataTransfer: true });
  listeners.change({ target: input });
  await flush();
  assert.equal(input.files[0].size, 12 * MB);
  assert.match(input.validity, /12\.0MB라 올릴 수 없어요/);
  assert.equal(input.nextElementSibling.textContent, input.validity);
});

test("DataTransfer가 없는 옛 브라우저는 원본을 그대로 둔다", async () => {
  const { listeners, input } = page({ fileSize: 6 * MB, outSize: 700 * 1024, dataTransfer: false });
  listeners.change({ target: input });
  await flush();
  assert.equal(input.files[0].name, "IMG_0001.JPG");
  assert.equal(input.validity, "");
});
