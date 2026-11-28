"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { isTrustedAppUrl } = require("./security.cjs");

test("allows the ODEI production route and nested ODEI pages", () => {
  assert.equal(isTrustedAppUrl("https://zurios.vercel.app/odeistudio?window=ide"), true);
  assert.equal(isTrustedAppUrl("https://zurios.vercel.app/odeistudio/nexus"), true);
  assert.equal(isTrustedAppUrl("https://zurios.vercel.app/odeistudio/"), true);
});

test("does not grant the desktop bridge to the Zuri OS root or sibling paths", () => {
  assert.equal(isTrustedAppUrl("https://zurios.vercel.app/"), false);
  assert.equal(isTrustedAppUrl("https://zurios.vercel.app/settings"), false);
  assert.equal(isTrustedAppUrl("https://zurios.vercel.app/odeistudio-evil"), false);
});

test("allows only the explicit local development origins", () => {
  assert.equal(isTrustedAppUrl("http://127.0.0.1:3002/?window=ide"), true);
  assert.equal(isTrustedAppUrl("http://localhost:3002/"), true);
  assert.equal(isTrustedAppUrl("http://localhost:3003/"), false);
});

test("rejects arbitrary origins, protocol downgrade and URL credentials", () => {
  assert.equal(isTrustedAppUrl("https://attacker.example/odeistudio"), false);
  assert.equal(isTrustedAppUrl("http://zurios.vercel.app/odeistudio"), false);
  assert.equal(isTrustedAppUrl("https://user:pass@zurios.vercel.app/odeistudio"), false);
  assert.equal(isTrustedAppUrl("not a URL"), false);
});
