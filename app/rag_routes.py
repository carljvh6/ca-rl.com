"""
RAG (Retrieval Augmented Generation) routes for experimentation
"""
import os
import json
import fitz  # PyMuPDF
from fasthtml.common import *
import markdown

# Don't import from main at module level to avoid circular imports
# layout and get_api_key will be imported inside register_rag_routes

# RAG dependencies (lazy loaded)
# COMMENTED OUT - Retrieval functionality temporarily disabled
# _chromadb_client = None
# _collection = None
# _initialized = False

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

# COMMENTED OUT - Retrieval functionality temporarily disabled
# def initialize_rag_system():
#     """Lazy initialization of RAG components using ChromaDB's default embedding (no torch needed)"""
#     global _chromadb_client, _collection, _initialized
#     
#     if _initialized:
#         return
#     
#     try:
#         import chromadb
#         
#         # Initialize ChromaDB with default embedding function (uses ONNX, no torch needed)
#         app_dir = os.path.dirname(os.path.abspath(__file__))
#         project_root = os.path.dirname(app_dir)
#         chroma_path = os.path.join(project_root, 'nedbank_chroma')
#         os.makedirs(chroma_path, exist_ok=True)
#         
#         _chromadb_client = chromadb.PersistentClient(path=chroma_path)
#         # Use default embedding function (all-MiniLM-L6-v2 via ONNX)
#         _collection = _chromadb_client.get_or_create_collection(
#             name="nedbank_reports"
#             # No embedding_function specified = uses default ONNX-based embedding
#         )
#         
#         # Check if collection is empty and needs to be populated
#         if _collection.count() == 0:
#             populate_chromadb()
#         
#         _initialized = True
#     except Exception as e:
#         print(f"Error initializing RAG system: {e}")
#         raise

# def split_text(txt, max_chars=2500, overlap=300):
#     """Split text into chunks with overlap"""
#     out = []
#     i = 0
#     while i < len(txt):
#         out.append(txt[i:i+max_chars])
#         i += max(1, max_chars - overlap)
#     return out

# def chunk_entry(entry):
#     """Chunk a JSON entry into documents and metadata"""
#     file, page, content = entry["file"], entry["page"], entry["content"]
#     docs, metas = [], []

#     def collect(node):
#         """Recursively collect text from nested structures"""
#         if isinstance(node, dict):
#             return " ".join(collect(v) for v in node.values())
#         if isinstance(node, list):
#             return " ".join(collect(v) for v in node)
#         return str(node)

#     for top_key, section_content in content.items():
#         section_text = collect(section_content)
#         if not section_text.strip():
#             continue
#         for piece in split_text(section_text):
#             docs.append(f"{top_key}\n{piece}")
#             metas.append({"file": file, "page": page, "section": top_key})
#     return docs, metas

# def populate_chromadb():
#     """Populate ChromaDB with embeddings from parsed PDF JSON
#     Uses ChromaDB's default embedding function (no torch needed)"""
#     global _collection
#     
#     app_dir = os.path.dirname(os.path.abspath(__file__))
#     project_root = os.path.dirname(app_dir)
#     json_path = os.path.join(project_root, 'static', 'rag', 'nedbank_int_2024_full_report_parsed.json')
#     
#     with open(json_path, "r") as f:
#         entries = json.load(f)
#     
#     all_docs, all_metas = [], []
#     for entry in entries:
#         d, m = chunk_entry(entry)
#         all_docs.extend(d)
#         all_metas.extend(m)
#     
#     # Add to ChromaDB - embeddings are generated automatically by default embedding function
#     # Process in batches to avoid memory issues
#     batch_size = 100
#     for i in range(0, len(all_docs), batch_size):
#         batch_docs = all_docs[i:i+batch_size]
#         batch_metas = all_metas[i:i+batch_size]
#         batch_ids = [f"doc_{j}" for j in range(i, min(i+batch_size, len(all_docs)))]
#         
#         _collection.add(
#             documents=batch_docs,
#             metadatas=batch_metas,
#             ids=batch_ids
#         )

# def retrieve(question, topk=5):
#     """Retrieve documents using ChromaDB's default embedding function
#     No reranking needed - ChromaDB handles similarity search"""
#     # ChromaDB will automatically embed the query using its default embedding function
#     results = _collection.query(
#         query_texts=[question],
#         n_results=topk
#     )
#     docs = results["documents"][0]
#     metas = results["metadatas"][0]
#     
#     return [(docs[i], metas[i]) for i in range(len(docs))]

# def answer_from_chunks(question, results):
#     """Generate answer from retrieved chunks using Gemini"""
#     from google import genai
#     
#     context = ""
#     for doc, meta in results:
#         page_label = f"[p.{meta['page']}]"
#         section = meta.get("section", "?")
#         context += f"{page_label} ({section})\n{doc}\n\n"
#     
#     user_prompt = f"""Answer the question using only the context. 
# Cite using the page-based labels, e.g. [p.91].

# Question: {question}

# Context:
# {context}"""
#     
#     api_key = get_api_key(use_secret_manager=True)
#     if not api_key:
#         return "Error: API key not configured. Please set GOOGLE_API_KEY environment variable."
#     
#     client = genai.Client(api_key=api_key)
#     
#     response = client.models.generate_content(
#         model="gemini-2.5-flash-lite",
#         contents=user_prompt
#     )
#     
#     return response.text

def register_rag_routes(rt):
    """Register all RAG routes with the provided rt decorator"""
    # Import here to avoid circular import
    from main import layout, get_api_key
    
    @rt('/rag')
    def get():
        """Main RAG page"""
        return layout(
            Div(
                H1('RAG (Retrieval Augmented Generation)', cls='text-3xl'),
                P('Under construction for now', cls='text-xl mt-4'),
            )
        )

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

    # COMMENTED OUT - Retrieval functionality temporarily disabled
    # @rt('/rag/retrieval')
    # def get():
    #     """RAG retrieval page with question input"""
    #     return layout(
    #         Div(
    #             H1('RAG Retrieval', cls='text-3xl mb-4'),
    #             P(
    #                 "Ask questions about the Nedbank 2024 Integrated Report. The system will retrieve relevant sections and generate answers using RAG.",
    #                 cls='prose prose-invert max-w-none mb-6'
    #             ),
    #             Form(
    #                 Div(
    #                     Label('Question', cls='label label-text mb-2'),
    #                     Textarea(
    #                         id='question',
    #                         name='question',
    #                         placeholder='Enter your question about the Nedbank report...',
    #                         cls='textarea textarea-bordered w-full h-24 text-base',
    #                         required=True
    #                     ),
    #                     cls='mb-4'
    #                 ),
    #                 Button('Ask Question', type='submit', cls='btn btn-primary'),
    #                 hx_post='/rag/retrieval_answer',
    #                 hx_target='#answer_area',
    #                 hx_swap='innerHTML',
    #                 hx_indicator='#loading'
    #             ),
    #             Div(
    #                 id='loading',
    #                 cls='htmx-indicator mt-4',
    #                 children=[
    #                     Div('Loading...', cls='text-center text-lg')
    #                 ]
    #             ),
    #             Div(
    #                 id='answer_area',
    #                 cls='mt-6'
    #             ),
    #         )
    #     )

    # @rt('/rag/retrieval_answer')
    # def post(question: str = None):
    #     """Handle RAG retrieval and answer generation"""
    #     if not question or not question.strip():
    #         return Div(
    #             P('Please enter a question.', cls='text-red-400'),
    #             cls='prose prose-invert max-w-none'
    #         )
    #     
    #     try:
    #         # Initialize RAG system if needed
    #         initialize_rag_system()
    #         
    #         # Retrieve relevant chunks (using ChromaDB's default embedding, no reranking)
    #         results = retrieve(question, topk=5)
    #         
    #         # Generate answer using Gemini
    #         answer = answer_from_chunks(question, results)
    #         
    #         # Convert markdown to HTML
    #         answer_html = markdown.markdown(answer, extensions=['nl2br', 'fenced_code'])
    #         
    #         # Format retrieved sources using FastHTML components
    #         sources_items = [
    #             Li(f"Page {meta['page']}, Section: {meta.get('section', '?')}")
    #             for doc, meta in results
    #         ]
    #         
    #         return Div(
    #             Div(
    #                 H3('Answer', cls='text-2xl mb-4'),
    #                 Div(answer_html, cls='prose prose-invert max-w-none'),
    #             ),
    #             Div(
    #                 H3('Sources', cls='text-xl mb-2 mt-6'),
    #                 Ul(*sources_items, cls='list-disc list-inside'),
    #             ),
    #             cls='prose prose-invert max-w-none'
    #         )
    #     except Exception as e:
    #         import traceback
    #         error_msg = f"Error processing question: {str(e)}"
    #         print(f"{error_msg}\n{traceback.format_exc()}")
    #         return Div(
    #             P(error_msg, cls='text-red-400'),
    #             Pre(traceback.format_exc(), cls='text-xs mt-2'),
    #             cls='prose prose-invert max-w-none'
    #         )