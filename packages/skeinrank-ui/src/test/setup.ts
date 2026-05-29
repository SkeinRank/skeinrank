import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

vi.stubEnv("VITE_SKEINRANK_ENABLE_LEGACY_WRITE_TOOLS", "true");
