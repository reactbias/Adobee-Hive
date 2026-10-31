import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);

// jsdom has no layout, so no scrolling API; the group chat scrolls itself to the newest message.
Element.prototype.scrollTo ??= function scrollTo() {};
