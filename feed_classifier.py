def build_html_snippet(processed_items, target_html_path="index.html"):
    """
    Safely injects live processed data table rows directly into the static index.html container
    """
    # Build only the inner data row markup elements
    rows_markup = ""
    for item in processed_items:
        cls = "badge-assess" if item["action"] == "Track & Assess" else ("badge-inform" if item["action"] == "Track & Inform" else "badge-nottracked")
        rows_markup += f"""
                        <tr>
                            <td><span class="reg-badge {cls}">{item['icon']} {item['action']}</span></td>
                            <td>
                                <a class="reg-link" href="{item['link']}" target="_blank">{item['title']}</a><br>
                                <span class="reg-tag">{item['category']}</span>
                                <p style="margin:4px 0 0 0; color:#475569; font-size:0.85rem;">{item['description'][:140]}...</p>
                            </td>
                            <td><em style="font-size:0.8rem; color:#64748b;">{item['justification']}</em></td>
                        </tr>"""

    if os.path.exists(target_html_path):
        with open(target_html_path, "r", encoding="utf-8") as file:
            content = file.read()
            
        # Target splice boundary anchors
        start_tag = '<tbody id="ai-classified-rows">'
        end_tag = '</tbody>'
        
        if start_tag in content and end_tag in content:
            before = content.split(start_tag)[0] + start_tag
            after = end_tag + content.split(end_tag)[1] # target second part split array safely
            
            # Reconstruct index file layout sequence preserving widget block architecture
            updated_html = before + rows_markup + after
            
            with open(target_html_path, "w", encoding="utf-8") as file:
                file.write(updated_html)
            print("Successfully compiled and synchronized index.html.")