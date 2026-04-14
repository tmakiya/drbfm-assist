with
    filtered_original_file as (
        select
            id
        from original_file
        order by
          created_at desc
        limit {limit}
    )

select
    ori.id as original_id,
    drw.id as drawing_id,
    drw.page_number,
    img.file_path
from filtered_original_file as ori
inner join drawing_page as drw on ori.id = drw.original_id
inner join drawing_png_image as img on drw.id = img.drawing_id
