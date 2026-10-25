export type ProjectTemplate = {id: string; name: string; description: string | null;
  phases: {title: string; start_offset: number | null; end_offset: number | null}[];
  source_project_title: string; created_by_name: string; created_at: string};
