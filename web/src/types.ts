export type Cloud = "solo_nube" | "local" | "siempre_local";

export type Entry = {
  path: string;
  parent: string | null;
  name: string;
  ext: string | null;
  is_dir: 0 | 1;
  size: number;
  files: number;
  mtime: number | null;
  cloud: Cloud | null;
  tags: string[];
  collapsed: 0 | 1;
  has_children?: 0 | 1;
  type: string | null;
  protected: boolean;
  user_tags?: string[];
  mode?: "completo" | "carpetas";
};

export type Project = { path: string; kinds: string; git_branch: string | null; git_dirty: 0 | 1 | null; last_activity: number | null };

export type EntryDetails = Entry & {
  ctime: number | null;
  atime: number | null;
  attrs: string[];
  hash_partial: string | null;
  hash_full: string | null;
  protected_reason: string | null;
  owner: string | null;
  mode: "completo" | "carpetas";
  project: Project | null;
  duplicates: string[];
  user_tags: string[];
  note: string;
};

export type Listing = { entry: Entry; mode: "completo" | "carpetas"; items: Entry[]; truncated: boolean };
