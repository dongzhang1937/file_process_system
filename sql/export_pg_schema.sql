--
-- PostgreSQL database dump
--


-- Dumped from database version 15.17
-- Dumped by pg_dump version 15.17

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: rag_chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rag_chunks (
    id integer NOT NULL,
    document_id integer NOT NULL,
    section_id integer NOT NULL,
    chunk_index integer DEFAULT 0,
    content text NOT NULL,
    content_length integer DEFAULT 0,
    content_hash character varying(64),
    embedding public.vector(1024),
    metadata jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: rag_chunks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rag_chunks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rag_chunks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rag_chunks_id_seq OWNED BY public.rag_chunks.id;


--
-- Name: rag_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rag_documents (
    id integer NOT NULL,
    filename character varying(500) NOT NULL,
    filepath character varying(1000),
    file_hash character varying(64),
    product_name character varying(200),
    doc_type character varying(100),
    total_sections integer DEFAULT 0,
    total_chunks integer DEFAULT 0,
    embedding_model character varying(100),
    status character varying(20) DEFAULT 'pending'::character varying,
    error_message text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    username character varying(100) DEFAULT 'asd'::character varying NOT NULL
);


--
-- Name: rag_documents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rag_documents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rag_documents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rag_documents_id_seq OWNED BY public.rag_documents.id;


--
-- Name: rag_sections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rag_sections (
    id integer NOT NULL,
    document_id integer NOT NULL,
    parent_section_id integer,
    title character varying(500),
    section_number character varying(50),
    heading_level integer DEFAULT 1,
    full_path text,
    content text,
    content_length integer DEFAULT 0,
    chunk_count integer DEFAULT 0,
    section_order integer DEFAULT 0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: rag_sections_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rag_sections_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rag_sections_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rag_sections_id_seq OWNED BY public.rag_sections.id;


--
-- Name: rag_chunks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_chunks ALTER COLUMN id SET DEFAULT nextval('public.rag_chunks_id_seq'::regclass);


--
-- Name: rag_documents id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_documents ALTER COLUMN id SET DEFAULT nextval('public.rag_documents_id_seq'::regclass);


--
-- Name: rag_sections id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_sections ALTER COLUMN id SET DEFAULT nextval('public.rag_sections_id_seq'::regclass);


--
-- Name: rag_chunks rag_chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_chunks
    ADD CONSTRAINT rag_chunks_pkey PRIMARY KEY (id);


--
-- Name: rag_documents rag_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_documents
    ADD CONSTRAINT rag_documents_pkey PRIMARY KEY (id);


--
-- Name: rag_sections rag_sections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_sections
    ADD CONSTRAINT rag_sections_pkey PRIMARY KEY (id);


--
-- Name: idx_rag_chunks_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_chunks_doc ON public.rag_chunks USING btree (document_id);


--
-- Name: idx_rag_chunks_embedding; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_chunks_embedding ON public.rag_chunks USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='200');


--
-- Name: idx_rag_chunks_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_chunks_hash ON public.rag_chunks USING btree (content_hash);


--
-- Name: idx_rag_chunks_section; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_chunks_section ON public.rag_chunks USING btree (section_id);


--
-- Name: idx_rag_docs_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_docs_hash ON public.rag_documents USING btree (file_hash);


--
-- Name: idx_rag_docs_product; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_docs_product ON public.rag_documents USING btree (product_name);


--
-- Name: idx_rag_docs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_docs_status ON public.rag_documents USING btree (status);


--
-- Name: idx_rag_docs_username; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_docs_username ON public.rag_documents USING btree (username);


--
-- Name: idx_rag_sections_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_sections_doc ON public.rag_sections USING btree (document_id);


--
-- Name: idx_rag_sections_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_sections_parent ON public.rag_sections USING btree (parent_section_id);


--
-- Name: rag_chunks rag_chunks_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_chunks
    ADD CONSTRAINT rag_chunks_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.rag_documents(id) ON DELETE CASCADE;


--
-- Name: rag_chunks rag_chunks_section_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_chunks
    ADD CONSTRAINT rag_chunks_section_id_fkey FOREIGN KEY (section_id) REFERENCES public.rag_sections(id) ON DELETE CASCADE;


--
-- Name: rag_sections rag_sections_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_sections
    ADD CONSTRAINT rag_sections_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.rag_documents(id) ON DELETE CASCADE;


--
-- Name: rag_sections rag_sections_parent_section_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_sections
    ADD CONSTRAINT rag_sections_parent_section_id_fkey FOREIGN KEY (parent_section_id) REFERENCES public.rag_sections(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--


