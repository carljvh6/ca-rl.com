"""
RAG (Retrieval Augmented Generation) routes for experimentation
"""
import os
import json
import fitz  # PyMuPDF
from fasthtml.common import *

# Import rt and layout from main
# This import happens after main.py creates rt and layout, so it should work
from main import rt, layout

def format_vlm_json_human_readable(json_data):
    """Convert VLM JSON to human-readable format"""
    content = json_data.get('content', {})
    title = content.get('title', '')
    description = content.get('description', '')
    sections = content.get('sections', [])
    
    lines = []
    
    if title:
        lines.append(f"# {title}\n")
    
    if description:
        lines.append(f"{description}\n")
    
    for section in sections:
        heading = section.get('heading', '')
        if heading:
            lines.append(f"\n## {heading}\n")
        
        section_desc = section.get('description', '')
        if section_desc:
            lines.append(f"{section_desc}\n")
        
        details = section.get('details', [])
        for detail in details:
            if 'statistic' in detail:
                stat = detail.get('statistic', '')
                desc = detail.get('description', '')
                if stat and desc:
                    lines.append(f"• {stat}: {desc}")
                elif stat:
                    lines.append(f"• {stat}")
            
            if 'statement' in detail:
                statement = detail.get('statement', '')
                if statement:
                    lines.append(f"• {statement}")
            
            if 'description' in detail and 'statistic' not in detail:
                desc = detail.get('description', '')
                if desc:
                    lines.append(f"• {desc}")
            
            references = detail.get('references', [])
            if references:
                ref_text = ", ".join(references)
                lines.append(f"  (References: {ref_text})")
        
        section_refs = section.get('references', [])
        if section_refs:
            ref_text = ", ".join(section_refs)
            lines.append(f"\n(References: {ref_text})\n")
    
    return "\n".join(lines)

@rt('/rag/ingestion')
def get():
    return layout(
        Div(
            H1('RAG (Retrieval Augmented Generation)', cls='text-3xl'),
            P(
                "Here we want to build a RAG system addressing the real-life problem of working with data in stylised PDFs. "
                "These PDFs often contain graphs and figures which are crucial to understanding, and our RAG ingestion system should be able to handle them.",
                cls='prose prose-invert max-w-none'
            ),
            P(
                "Here is an example of a stylised PDF, we chose the Nedbank annual report 2024 to have a go at looking at financial data and how to ingest it into a RAG system.",
                cls='prose prose-invert max-w-none'
            ),
            Img(src='/static/rag/nedbank_ex_page.png', alt='Nedbank Report Example Page', cls='mt-4 w-3/4 h-auto'),
            Div(
                H2('Analysis Method', cls='text-2xl mt-8 mb-4'),
                Div(
                    Label(
                        Input(type='radio', name='analysis_method', value='pdf_parsing', id='pdf_parsing', 
                              hx_get='/rag/analysis_text?analysis_method=pdf_parsing', hx_target='#analysis_text_area', 
                              hx_trigger='change', hx_swap='innerHTML'),
                        ' PDF Parsing',
                        cls='label cursor-pointer'
                    ),
                    Label(
                        Input(type='radio', name='analysis_method', value='vlm_json', id='vlm_json', 
                              hx_get='/rag/analysis_text?analysis_method=vlm_json', hx_target='#analysis_text_area', 
                              hx_trigger='change', hx_swap='innerHTML'),
                        ' Vision-language model analysis - JSON',
                        cls='label cursor-pointer'
                    ),
                    Label(
                        Input(type='radio', name='analysis_method', value='vlm_human', id='vlm_human', 
                              hx_get='/rag/analysis_text?analysis_method=vlm_human', hx_target='#analysis_text_area', 
                              hx_trigger='change', hx_swap='innerHTML'),
                        ' Vision-language model analysis - human readable',
                        cls='label cursor-pointer'
                    ),
                    cls='flex flex-col gap-2 mb-4'
                ),
                Div(
                    id='analysis_text_area',
                    children=[
                        Textarea(
                            placeholder='Select an analysis method above to see details...',
                            cls='textarea textarea-bordered w-full h-64 text-base',
                            readonly=True
                        )
                    ]
                ),
                cls='mt-8'
            ),
        )
    )

@rt('/rag/analysis_text')
def get(analysis_method: str = None):
    """Return the analysis text based on the selected method"""
    if analysis_method == 'pdf_parsing':
        # Extract text from page 9 of the Nedbank PDF
        try:
            # Get the path to the PDF file
            app_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(app_dir)
            pdf_path = os.path.join(project_root, 'static', 'rag', 'nedbank_int_2024.pdf')
            
            # Open PDF and extract page 9 (0-indexed, so page 8)
            doc = fitz.open(pdf_path)
            page = doc[8]  # Page 9 is index 8
            text = page.get_text()
            doc.close()
            
            # Return a textarea with the extracted text
            return Textarea(
                text,
                cls='textarea textarea-bordered w-full h-64 text-base',
                readonly=True
            )
        except Exception as e:
            return Textarea(
                f"Error extracting text from PDF: {str(e)}",
                cls='textarea textarea-bordered w-full h-64 text-base',
                readonly=True
            )
    elif analysis_method == 'vlm_json':
        # Load and display the VLM parsed JSON
        try:
            # Get the path to the JSON file
            app_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(app_dir)
            json_path = os.path.join(project_root, 'static', 'rag', 'nedbank_ex_parsed_pdf.json')
            
            # Load JSON file
            with open(json_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            # Format JSON with indentation for readability
            formatted_json = json.dumps(json_data, indent=2, ensure_ascii=False)
            
            return Textarea(
                formatted_json,
                cls='textarea textarea-bordered w-full h-64 text-base font-mono text-sm',
                readonly=True
            )
        except Exception as e:
            return Textarea(
                f"Error loading VLM parsed JSON: {str(e)}",
                cls='textarea textarea-bordered w-full h-64 text-base',
                readonly=True
            )
    elif analysis_method == 'vlm_human':
        # Load and display the VLM parsed JSON in human-readable format
        try:
            # Get the path to the JSON file
            app_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(app_dir)
            json_path = os.path.join(project_root, 'static', 'rag', 'nedbank_ex_parsed_pdf.json')
            
            # Load JSON file
            with open(json_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            # Convert to human-readable format
            human_readable = format_vlm_json_human_readable(json_data)
            
            return Textarea(
                human_readable,
                cls='textarea textarea-bordered w-full h-64 text-base',
                readonly=True
            )
        except Exception as e:
            return Textarea(
                f"Error loading VLM parsed JSON: {str(e)}",
                cls='textarea textarea-bordered w-full h-64 text-base',
                readonly=True
            )
    else:
        return Textarea(
            "Select an analysis method above to see details...",
            cls='textarea textarea-bordered w-full h-64 text-base',
            readonly=True
        )