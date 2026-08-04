import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { AVirtualList } from "./large-data";

it("renders only a small visible window for a 5,000-item list", () => {
  const items = Array.from({ length: 5_000 }, (_, index) => `item-${index}`);
  render(<AVirtualList items={items} viewportHeight={80} renderItem={(item) => item} />);
  expect(screen.getAllByRole("listitem")).toHaveLength(12);
  fireEvent.scroll(screen.getByRole("list"), { target: { scrollTop: 4_000 } });
  expect(screen.getByText("item-100")).toBeInTheDocument();
});
