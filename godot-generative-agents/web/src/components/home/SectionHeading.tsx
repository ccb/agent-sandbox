import type { ReactNode } from "react";
import { sectionNumber } from "./toc";

type Props = {
  id: string;
  level: 2 | 3;
  className?: string;
  children: ReactNode;
};

/** A numbered h2/h3 whose prefix is looked up from the shared contents nav. */
export function SectionHeading({ id, level, className, children }: Props) {
  const Tag = level === 2 ? "h2" : "h3";
  const num = sectionNumber(id);
  return (
    <Tag id={id} className={className}>
      {num !== undefined && <span className="nrf-secnum">{num} </span>}
      {children}
    </Tag>
  );
}
