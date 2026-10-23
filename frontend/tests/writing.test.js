/* Unit tests for the SOP & LOR helpers (`npm test`). */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  aiBlockReason, answeredCount, draftFilename, limitState, placeholderCount, refereeStage, sopStep, statementStatus, wordCount,
} from "../src/lib/writing.js";

const QUESTIONS = [{ key: "motivation", required: true }, { key: "goals", required: true }, { key: "extra", required: false }];

describe("writing", () => {
  it("counts words and placeholders like the backend", () => {
    assert.equal(wordCount(""), 0);
    assert.equal(wordCount("  Dear   committee,\n\nI am "), 4);
    assert.equal(placeholderCount("I led [ADD: project name] at [ADD: company]. [not a gap]"), 2);
  });

  it("describes progress against the word limit", () => {
    assert.equal(limitState(1100, 1000).state, "over");
    assert.match(limitState(1100, 1000).text, /100 over/);
    assert.equal(limitState(950, 1000).state, "near");
    assert.equal(limitState(300, 1000).state, "short");
    assert.equal(limitState(0, 1000).state, "ok");
    assert.equal(limitState(700, 1000).pct, 70);
  });

  it("finds the step of the guided flow", () => {
    assert.equal(sopStep({ status: "Draft", answers: {}, content: "" }, QUESTIONS), 1);
    assert.equal(sopStep({ status: "Draft", answers: { motivation: "a", goals: "b" }, content: "" }, QUESTIONS), 2);
    assert.equal(sopStep({ status: "Draft", answers: {}, content: "some text" }, QUESTIONS), 3);
    assert.equal(sopStep({ status: "Final", content: "x" }, QUESTIONS), 4);
    assert.equal(answeredCount(QUESTIONS, { motivation: " x ", goals: "  " }), 1);
  });

  it("explains why AI is unavailable", () => {
    assert.match(aiBlockReason({ canEdit: false }), /counsellor/);
    assert.match(aiBlockReason({ canEdit: true, aiAvailable: false }), /not set up/);
    assert.match(aiBlockReason({ canEdit: true, aiAvailable: true, consent: { granted: false } }), /not agreed/);
    assert.equal(aiBlockReason({ canEdit: true, aiAvailable: true, consent: { granted: true } }), "");
  });

  it("labels statuses and referee stages for people", () => {
    assert.equal(statementStatus("Shared").label, "Shared with student");
    assert.equal(refereeStage("Requested").label, "Waiting for letter");
    assert.equal(refereeStage("Unknown").label, "Unknown");
  });

  it("makes safe download names", () => {
    assert.equal(draftFilename('SOP - CS: "AI"/ML'), "SOP - CS AI ML.txt");
    assert.equal(draftFilename(""), "draft.txt");
  });
});
