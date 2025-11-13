"""Generate a standalone HTML export page for a research session."""
import json
import sys
import base64
from pathlib import Path
from datetime import datetime

# Load session data directly from JSON
def load_session_data(session_id):
    """Load session data from JSON file."""
    session_file = Path(__file__).parent.parent / "data" / "research" / "sessions" / f"session_{session_id}.json"
    with open(session_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_logo_as_base64():
    """Load logo file and convert to base64 data URI."""
    logo_path = Path(__file__).parent.parent / "client" / "public" / "logo.png"
    try:
        with open(logo_path, 'rb') as f:
            logo_data = base64.b64encode(f.read()).decode('utf-8')
            return f"data:image/png;base64,{logo_data}"
    except Exception as e:
        print(f"⚠️  Warning: Could not load logo: {e}")
        return ""


def escape_html(text):
    """Escape HTML special characters."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def deduplicate_text(text):
    """Remove duplicate or near-duplicate text blocks separated by double newlines."""
    if not text:
        return ""
    
    # Split by double newlines
    blocks = text.split('\n\n')
    
    # Get non-empty blocks
    non_empty_blocks = [b.strip() for b in blocks if b.strip()]
    
    # If less than 2 blocks, nothing to deduplicate
    if len(non_empty_blocks) < 2:
        return text
    
    # Check if all blocks are identical (exact match)
    if len(set(non_empty_blocks)) == 1:
        return non_empty_blocks[0]
    
    # Check if blocks are near-duplicates (>90% similarity)
    # Calculate similarity based on character overlap
    first_block = non_empty_blocks[0]
    all_similar = True
    
    for block in non_empty_blocks[1:]:
        # Calculate simple character-level similarity
        if len(first_block) == 0 or len(block) == 0:
            all_similar = False
            break
        
        # Count matching characters at same positions
        min_len = min(len(first_block), len(block))
        max_len = max(len(first_block), len(block))
        matches = sum(1 for i in range(min_len) if first_block[i] == block[i])
        similarity = matches / max_len
        
        if similarity < 0.90:  # 90% threshold
            all_similar = False
            break
    
    if all_similar:
        # All blocks are near-duplicates, return just the first one
        return non_empty_blocks[0]
    
    # Otherwise return the original text
    return text


def format_bold(text):
    """Convert **text** to <strong>text</strong> for proper bold rendering."""
    if not text:
        return ""
    
    # First deduplicate if needed
    deduplicated = deduplicate_text(text)
    
    # Then escape HTML
    escaped = escape_html(deduplicated)
    
    # Then convert **text** to <strong>text</strong>
    import re
    # Match **text** pattern (non-greedy)
    formatted = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)
    
    return formatted


def deduplicate_list(items):
    """Remove duplicate items from a list while preserving order."""
    if not items:
        return []
    
    seen = []
    seen_strs = set()
    
    for item in items:
        # Convert item to string for comparison
        if isinstance(item, dict):
            item_str = str(sorted(item.items()))
        else:
            item_str = str(item)
        
        # Only add if we haven't seen it before
        if item_str not in seen_strs:
            seen.append(item)
            seen_strs.add(item_str)
    
    return seen


def extract_content(step):
    """Extract structured content from a step."""
    findings_root = step.get("findings", {})
    findings = findings_root.get("findings", findings_root) if isinstance(findings_root, dict) else findings_root
    poi = findings.get("points_of_interest", {}) if isinstance(findings, dict) else {}
    analysis = findings.get("analysis_details", {}) if isinstance(findings, dict) else {}
    
    return {
        "summary": findings.get("summary") if isinstance(findings, dict) else None,
        "article": findings.get("article") if isinstance(findings, dict) else None,
        "key_claims": deduplicate_list(poi.get("key_claims", [])),
        "notable_evidence": deduplicate_list(poi.get("notable_evidence", [])),
        "five_whys": deduplicate_list(analysis.get("five_whys", [])),
        "assumptions": deduplicate_list(analysis.get("assumptions", [])),
        "uncertainties": deduplicate_list(analysis.get("uncertainties", [])),
        "insights": step.get("insights"),
        "confidence": step.get("confidence"),
    }


def format_timestamp(timestamp):
    """Format timestamp string."""
    if not timestamp:
        return ""
    try:
        dt = datetime.fromisoformat(timestamp)
        return f"Updated {dt.strftime('%Y-%m-%d %H:%M')}"
    except:
        return timestamp


def generate_html(session_id: str, output_path: str):
    """Generate HTML export for a session."""
    # Load session and logo
    session_data = load_session_data(session_id)
    logo_base64 = load_logo_as_base64()
    
    metadata = session_data.get("metadata", {})
    scratchpad = session_data.get("scratchpad", {})
    phase4 = session_data.get("phase_artifacts", {}).get("phase4", {}).get("data", {})
    
    # Extract data
    synthesized_goal = metadata.get("synthesized_goal", {})
    research_objective = (
        synthesized_goal.get("comprehensive_topic") or
        metadata.get("selected_goal") or 
        metadata.get("user_topic") or 
        "未提供研究目标"
    )
    batch_id = metadata.get("batch_id")
    final_report = phase4.get("report_content") or phase4.get("final_report") or metadata.get("final_report") or "最终报告尚未生成。"
    research_plan = metadata.get("research_plan", [])
    
    # Extract steps
    steps = []
    for key in sorted(scratchpad.keys()):
        entry = scratchpad[key]
        if entry and entry.get("step_id"):
            steps.append(entry)
    
    # Start HTML
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Research Report - {session_id}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    colors: {{
                        primary: {{
                            500: '#FEC74A',
                            600: '#D4A03D',
                            200: '#FFF2CC',
                        }},
                        neutral: {{
                            black: '#031C34',
                            800: '#1E3A4D',
                            700: '#365566',
                            600: '#4D6B7E',
                            500: '#5D87A1',
                            400: '#9EB7C7',
                            300: '#DFE7EC',
                            200: '#E7EDF1',
                            100: '#F0F3F6',
                            50: '#F8F7F9',
                            white: '#FFFFFF',
                        }},
                        yellow: {{
                            50: '#FEFCE8',
                            100: '#FEF3C7',
                            500: '#EAB308',
                            800: '#92400E',
                        }},
                    }}
                }}
            }}
        }}
    </script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            font-size: 15px;
            line-height: 1.7;
        }}
        
        p, li {{
            line-height: 1.8;
            margin-bottom: 0.75rem;
        }}
        
        h1, h2, h3, h4, h5 {{
            line-height: 1.4;
        }}
        
        .section-spacing {{
            margin-bottom: 1.25rem;
        }}
        
        .toc-link {{
            text-decoration: none;
            color: inherit;
            transition: color 0.2s;
        }}
        
        .toc-link:hover {{
            color: #D4A03D;
        }}
        
        /* Mobile optimizations */
        @media (max-width: 768px) {{
            .mobile-no-side-padding {{
                padding-left: 0 !important;
                padding-right: 0 !important;
            }}
            
            body {{
                font-size: 14px;
            }}
            
            .max-w-4xl {{
                padding-left: 0.5rem !important;
                padding-right: 0.5rem !important;
            }}
            
            /* Mobile navigation bar */
            .no-print {{
                padding-top: 0.375rem !important;
                padding-bottom: 0.375rem !important;
            }}
            
            .no-print .max-w-6xl {{
                padding-left: 0.75rem !important;
                padding-right: 0.75rem !important;
                padding-top: 0.375rem !important;
                padding-bottom: 0.375rem !important;
            }}
            
            .no-print img {{
                height: 1.5rem !important; /* h-6 for mobile */
                display: block !important;
            }}
            
            .no-print button {{
                padding: 0.375rem 0.75rem !important;
                font-size: 0.8125rem !important;
            }}
        }}
        
        @media print {{
            @page {{
                size: A4;
                margin: 1.5cm;
            }}
            
            body {{
                print-color-adjust: exact;
                -webkit-print-color-adjust: exact;
            }}
            
            .no-print {{
                display: none !important;
            }}
            
            .avoid-break {{
                page-break-inside: avoid;
            }}
        }}
    </style>
</head>
<body class="bg-neutral-50">
    <script>
        // Initialize Lucide icons when page loads
        document.addEventListener('DOMContentLoaded', () => {{
            lucide.createIcons();
        }});
    </script>
    <!-- Print controls -->
    <div class="no-print sticky top-0 z-50 bg-white border-b border-neutral-300 shadow-sm">
        <div class="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
            <div class="flex items-center gap-3">
                {"" if not logo_base64 else f'<img src="{logo_base64}" alt="Deep Insights" class="h-16" />'}
            </div>
            <button onclick="window.print()" class="px-6 py-2 bg-primary-500 text-white rounded-full hover:bg-primary-600 transition">
                打印/导出 PDF
            </button>
        </div>
    </div>

    <!-- Report content -->
    <div class="max-w-4xl mx-auto px-8 py-12">
        <!-- Cover -->
        <div class="mb-12 avoid-break">
            <div class="flex items-center justify-between mb-8">
                <h1 class="text-3xl font-bold text-neutral-black">Deep Insights Tool</h1>
            </div>
            <div class="border-t-4 border-primary-500 pt-8">
                <h2 class="text-2xl font-bold text-neutral-800 mb-4">研究报告</h2>
                <div class="space-y-2 text-sm text-neutral-600">
                    <p>Session ID: {session_id}</p>
"""
    
    if batch_id:
        html += f"                    <p>Batch ID: {batch_id}</p>\n"
    
    html += f"""                    <p>导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
            </div>
        </div>

        <!-- Research Objective -->
        <section class="mb-12 avoid-break">
            <h2 class="text-xl font-bold text-neutral-800 mb-5">Research Objective</h2>
            <div class="bg-white rounded-lg border border-neutral-300 p-8">
                <p class="text-xl font-bold text-neutral-800 whitespace-pre-wrap leading-relaxed">{format_bold(research_objective)}</p>
            </div>
        </section>

        <!-- Table of Contents -->
        <section class="mb-12 avoid-break">
            <h2 class="text-xl font-bold text-neutral-800 mb-5">目录</h2>
            <div class="bg-white rounded-lg border border-neutral-300 overflow-hidden shadow-sm">
                <table class="min-w-full table-fixed">
                    <thead>
                        <tr class="bg-neutral-50 border-b-2 border-neutral-300">
                            <th class="w-20 px-6 py-4 text-left text-sm font-semibold text-neutral-800"></th>
                            <th class="px-6 py-4 text-left text-sm font-semibold text-neutral-800">研究问题</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-neutral-200">
"""
    
    # Generate TOC entries
    for idx, step in enumerate(steps, 1):
        step_id = step.get("step_id")
        plan = next((p for p in research_plan if p.get("step_id") == step_id), {})
        title = format_bold(plan.get("goal") or f"研究问题 {step_id}")
        
        html += f"""
                        <tr class="hover:bg-neutral-50 transition-colors">
                            <td class="px-6 py-5 text-base text-primary-600 font-semibold align-top">
                                <a href="#step-{idx}" class="toc-link">{idx}</a>
                            </td>
                            <td class="px-6 py-5 text-base text-neutral-700 leading-relaxed">
                                <a href="#step-{idx}" class="toc-link hover:text-primary-600 transition-colors">{title}</a>
                            </td>
                        </tr>
"""
    
    html += f"""
                        <tr class="bg-neutral-50 hover:bg-neutral-100 transition-colors">
                            <td class="px-6 py-5 text-base text-primary-600 font-semibold align-top">
                                <a href="#final-report" class="toc-link">总结</a>
                            </td>
                            <td class="px-6 py-5 text-base text-neutral-700 leading-relaxed">
                                <a href="#final-report" class="toc-link hover:text-primary-600 transition-colors">AI增强战略思维的边界与效能</a>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </section>

        <!-- Phase 3 Steps -->
        <section class="mb-12">
            <h2 class="text-xl font-bold text-neutral-800 mb-4">研究问题</h2>
            <div class="space-y-6">
"""
    
    # Add steps
    for idx, step in enumerate(steps, 1):
        step_id = step.get("step_id")
        plan = next((p for p in research_plan if p.get("step_id") == step_id), {})
        title = format_bold(plan.get("goal") or f"研究问题 {step_id}")
        content = extract_content(step)
        timestamp = format_timestamp(step.get("timestamp"))
        
        html += f"""
                <div id="step-{idx}" class="bg-white rounded-lg border border-neutral-200 p-7 avoid-break section-spacing" style="padding: 1.75rem;">
                    <div class="mb-5 pb-4 border-b border-neutral-200">
                        <h3 class="text-lg font-semibold text-neutral-800 mb-2">{idx}. {title}</h3>
"""
        
        if timestamp:
            html += f"                        <p class=\"text-xs text-neutral-500\">{timestamp}</p>\n"
        
        if content["confidence"] is not None:
            conf_pct = int(content["confidence"] * 100)
            html += f"                        <div class=\"mt-2 inline-block px-3 py-1 bg-yellow-100 text-yellow-800 text-xs font-medium rounded-full\">Confidence: {conf_pct}%</div>\n"
        
        html += "                    </div>\n"
        
        # Summary
        if content["summary"]:
            html += f"""
                    <div class="mb-5">
                        <h4 class="text-base font-semibold text-neutral-800 mb-3 flex items-center">
                            <i data-lucide="edit" class="w-4 h-4 mr-2"></i>
                            摘要
                        </h4>
                        <p class="text-neutral-700 whitespace-pre-wrap leading-relaxed">{format_bold(content["summary"])}</p>
                    </div>
"""
        
        # Key Claims
        if content["key_claims"]:
            html += """
                    <div class="mb-5">
                        <h4 class="text-base font-semibold text-neutral-800 mb-3 flex items-center">
                            <i data-lucide="key" class="w-4 h-4 mr-2"></i>
                            主要观点
                        </h4>
                        <div class="space-y-3">
"""
            for claim in content["key_claims"]:
                html += f"""
                            <div class="bg-neutral-50 rounded p-4">
                                <p class="font-medium text-neutral-800 leading-relaxed">{format_bold(claim.get('claim', ''))}</p>
"""
                if claim.get("supporting_evidence"):
                    html += f"""
                                <p class="text-sm text-neutral-600 mt-2 leading-relaxed">
                                    <span class="font-medium">证据支持：</span>{format_bold(claim['supporting_evidence'])}
                                </p>
"""
                html += "                            </div>\n"
            html += "                        </div>\n                    </div>\n"
        
        # Notable Evidence
        if content["notable_evidence"]:
            html += """
                    <div class="mb-5">
                        <h4 class="text-base font-semibold text-neutral-800 mb-3 flex items-center">
                            <i data-lucide="chart-bar" class="w-4 h-4 mr-2"></i>
                            重要发现
                        </h4>
                        <div class="space-y-3">
"""
            for ev in content["notable_evidence"]:
                html += "                            <div class=\"bg-neutral-50 rounded p-4\">\n"
                if ev.get("evidence_type"):
                    html += f"                                <span class=\"inline-block px-2 py-1 bg-yellow-100 text-yellow-800 text-xs font-medium rounded mr-2 mb-1\">{format_bold(ev['evidence_type'])}</span>\n"
                html += f"                                <p class=\"text-neutral-700 leading-relaxed\">{format_bold(ev.get('description', ''))}</p>\n"
                html += "                            </div>\n"
            html += "                        </div>\n                    </div>\n"
        
        # Article
        if content["article"]:
            html += f"""
                    <div class="mb-5">
                        <h4 class="text-base font-semibold text-neutral-800 mb-3 flex items-center">
                            <i data-lucide="file-text" class="w-4 h-4 mr-2"></i>
                            深度文章
                        </h4>
                        <p class="text-neutral-700 whitespace-pre-wrap leading-relaxed">{format_bold(content["article"])}</p>
                    </div>
"""
        
        # Analysis
        if content["five_whys"] or content["assumptions"] or content["uncertainties"]:
            html += """
                    <div class="mb-5 bg-neutral-100 rounded p-5">
                        <h4 class="text-base font-semibold text-neutral-800 mb-4 flex items-center">
                            <i data-lucide="search" class="w-4 h-4 mr-2"></i>
                            Q&A
                        </h4>
"""
            
            if content["five_whys"]:
                html += "                        <div class=\"mb-4\">\n"
                html += "                            <h5 class=\"text-sm font-semibold text-neutral-700 mb-3\">Five Whys</h5>\n"
                html += "                            <div class=\"space-y-3\">\n"
                for item in content["five_whys"]:
                    html += f"""
                                <div class="text-sm leading-relaxed">
                                    <p class="font-medium text-neutral-800 mb-1">Q: {format_bold(item.get('question', ''))}</p>
                                    <p class="text-neutral-600">A: {format_bold(item.get('answer', ''))}</p>
                                </div>
"""
                html += "                            </div>\n                        </div>\n"
            
            if content["assumptions"]:
                html += """
                        <div class="mb-4">
                            <h5 class="text-sm font-semibold text-neutral-700 mb-3">本分析有何假设？</h5>
                            <ul class="list-disc list-inside text-sm text-neutral-600 space-y-2 leading-relaxed">
"""
                for assumption in content["assumptions"]:
                    html += f"                                <li class=\"ml-2\">{format_bold(assumption)}</li>\n"
                html += "                            </ul>\n                        </div>\n"
            
            if content["uncertainties"]:
                html += """
                        <div>
                            <h5 class="text-sm font-semibold text-neutral-700 mb-3">有什么未能确定？</h5>
                            <ul class="list-disc list-inside text-sm text-neutral-600 space-y-2 leading-relaxed">
"""
                for uncertainty in content["uncertainties"]:
                    html += f"                                <li class=\"ml-2\">{format_bold(uncertainty)}</li>\n"
                html += "                            </ul>\n                        </div>\n"
            
            html += "                    </div>\n"
        
        # Insights
        if content["insights"]:
            html += f"""
                    <div class="bg-yellow-50 border-l-4 border-yellow-500 rounded p-5">
                        <h4 class="text-base font-semibold text-neutral-800 mb-3 flex items-center">
                            <i data-lucide="lightbulb" class="w-4 h-4 mr-2"></i>
                            洞察
                        </h4>
                        <p class="text-neutral-700 whitespace-pre-wrap leading-relaxed">{format_bold(content["insights"])}</p>
                    </div>
"""
        
        html += "                </div>\n"
    
    html += """
            </div>
        </section>

        <!-- Final Report -->
        <section id="final-report" class="mb-12">
            <h2 class="text-xl font-bold text-neutral-800 mb-5">总结</h2>
            <div class="bg-white rounded-lg border border-neutral-300 p-8" style="padding: 2rem;">
"""
    
    # Add final report (simple markdown rendering)
    # Skip metadata section (研究报告 header and first few lines with metadata)
    skip_until_content = True
    in_metadata = False
    
    for line in final_report.split('\n'):
        line = line.strip()
        
        # Detect and skip metadata section
        if skip_until_content:
            # Skip lines like "研究报告", "研究目标:", "生成时间:", "批次ID:" etc
            if line in ['研究报告', ''] or line.startswith('研究目标:') or line.startswith('生成时间:') or line.startswith('批次ID:'):
                continue
            # Once we hit a content heading (## or lower), start rendering
            elif line.startswith('##') or line.startswith('当AI开始'):
                skip_until_content = False
            else:
                continue
        
        # Render content
        if not line:
            html += '                    <div class="h-5"></div>\n'
        elif line.startswith('# '):
            html += f'                    <h1 class="text-2xl font-bold text-neutral-800 mt-8 mb-5 leading-tight">{escape_html(line[2:])}</h1>\n'
        elif line.startswith('## '):
            html += f'                    <h2 class="text-xl font-semibold text-neutral-800 mt-6 mb-4 leading-tight">{escape_html(line[3:])}</h2>\n'
        elif line.startswith('### '):
            html += f'                    <h3 class="text-lg font-semibold text-neutral-800 mt-5 mb-3 leading-tight">{escape_html(line[4:])}</h3>\n'
        elif line.startswith('- '):
            html += f'                    <li class="text-neutral-700 ml-4 mb-2 leading-relaxed">{format_bold(line[2:])}</li>\n'
        else:
            html += f'                    <p class="text-neutral-700 mb-4 whitespace-pre-wrap leading-relaxed">{format_bold(line)}</p>\n'
    
    html += """
            </div>
        </section>
    </div>
</body>
</html>
"""
    
    # Write file
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(f"Generated HTML export: {output.absolute()}")
    print(f"   File size: {output.stat().st_size:,} bytes")
    print(f"   Open in browser and use Ctrl+P (Cmd+P) to print to PDF")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate HTML export for a research session')
    parser.add_argument('session_id', nargs='?', default='20251110_192142', help='Session ID to export')
    parser.add_argument('--output', '-o', default='downloads/research-report-export.html', help='Output HTML file path')
    parser.add_argument('--upload', action='store_true', help='Upload to Alibaba Cloud OSS after generation')
    parser.add_argument('--upload-only', action='store_true', help='Skip generation and only upload existing file')
    
    args = parser.parse_args()
    
    # Generate HTML if not upload-only
    if not args.upload_only:
        generate_html(args.session_id, args.output)
    elif not Path(args.output).exists():
        print(f"Error: File not found for upload: {args.output}")
        print("   Use --upload without --upload-only to generate first.")
        sys.exit(1)
    
    # Upload if requested
    if args.upload or args.upload_only:
        print("\n" + "="*60)
        print("Uploading to Alibaba Cloud OSS...")
        print("="*60)
        
        try:
            # Add parent directory to path to import services
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from services.oss_upload_service import OSSUploadService
            
            # Create service and upload
            service = OSSUploadService()
            result = service.upload_html_report(
                args.output,
                session_id=args.session_id
            )
            
            if result:
                print("\n" + "="*60)
                print("HTML Report Successfully Uploaded!")
                print("="*60)
                print(f"Public URL: {result['url']}")
                print(f"Object Key: {result['object_key']}")
                print(f"Bucket: {result['bucket']}")
                print(f"Size: {result['size_bytes']:,} bytes ({result['size_bytes']/(1024*1024):.2f} MB)")
                print("Access: Public (anyone with link can access)")
                print("\nShare this link to let others view your research report!")
                print("="*60)
            else:
                print("\nUpload failed. Check the error messages above.")
                sys.exit(1)
                
        except ImportError as e:
            print(f"\nError: Could not import OSSUploadService: {e}")
            print("   Make sure you're running from the project root directory.")
            sys.exit(1)
        except Exception as e:
            print(f"\nUnexpected error during upload: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

