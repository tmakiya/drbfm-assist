select
    drawing_id,
    components_theme,
    issue_theme,
    technology_theme,
    project,
    ocr_text_snippet
from
  `{table_fqn}`
order by
  drawing_id
