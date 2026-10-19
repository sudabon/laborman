import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// vitest の globals を使っていないため、Testing Library の自動クリーンアップを明示的に登録する
afterEach(() => {
  cleanup();
});
