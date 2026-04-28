--
-- PostgreSQL database dump
--

\restrict ocP0aM8tpNfMggAhAxCZhpttFOGvPjDyKeIPgzNZVk4wGWXnz7ybgsMRbESVOpo

-- Dumped from database version 18.3
-- Dumped by pg_dump version 18.3

-- Started on 2026-04-28 01:24:23

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 220 (class 1259 OID 32963)
-- Name: User; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public."User" (
    uid integer NOT NULL,
    email text NOT NULL,
    username text NOT NULL,
    nickname text,
    password text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public."User" OWNER TO postgres;

--
-- TOC entry 219 (class 1259 OID 32962)
-- Name: User_uid_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public."User_uid_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public."User_uid_seq" OWNER TO postgres;

--
-- TOC entry 4983 (class 0 OID 0)
-- Dependencies: 219
-- Name: User_uid_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public."User_uid_seq" OWNED BY public."User".uid;


--
-- TOC entry 225 (class 1259 OID 33027)
-- Name: channel; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.channel (
    name text NOT NULL,
    wid integer NOT NULL,
    type text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by integer NOT NULL,
    CONSTRAINT channel_type_check CHECK ((type = ANY (ARRAY['public'::text, 'private'::text, 'direct'::text])))
);


ALTER TABLE public.channel OWNER TO postgres;

--
-- TOC entry 227 (class 1259 OID 33052)
-- Name: channelmember; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.channelmember (
    cmid integer NOT NULL,
    wmid integer NOT NULL,
    channel_name text NOT NULL,
    channel_wid integer NOT NULL,
    invited_at timestamp with time zone,
    joined_at timestamp with time zone
);


ALTER TABLE public.channelmember OWNER TO postgres;

--
-- TOC entry 226 (class 1259 OID 33051)
-- Name: channelmember_cmid_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.channelmember_cmid_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.channelmember_cmid_seq OWNER TO postgres;

--
-- TOC entry 4984 (class 0 OID 0)
-- Dependencies: 226
-- Name: channelmember_cmid_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.channelmember_cmid_seq OWNED BY public.channelmember.cmid;


--
-- TOC entry 229 (class 1259 OID 33077)
-- Name: message; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.message (
    mid integer NOT NULL,
    content text NOT NULL,
    sent_at timestamp with time zone DEFAULT now() NOT NULL,
    channel_name text NOT NULL,
    channel_wid integer NOT NULL,
    cmid integer NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    is_recalled boolean DEFAULT false,
    is_deleted boolean DEFAULT false
);


ALTER TABLE public.message OWNER TO postgres;

--
-- TOC entry 230 (class 1259 OID 33132)
-- Name: message_hidden; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.message_hidden (
    mid integer NOT NULL,
    uid integer NOT NULL
);


ALTER TABLE public.message_hidden OWNER TO postgres;

--
-- TOC entry 228 (class 1259 OID 33076)
-- Name: message_mid_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.message_mid_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.message_mid_seq OWNER TO postgres;

--
-- TOC entry 4985 (class 0 OID 0)
-- Dependencies: 228
-- Name: message_mid_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.message_mid_seq OWNED BY public.message.mid;


--
-- TOC entry 222 (class 1259 OID 32982)
-- Name: workspace; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.workspace (
    wid integer NOT NULL,
    name text NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by integer NOT NULL
);


ALTER TABLE public.workspace OWNER TO postgres;

--
-- TOC entry 221 (class 1259 OID 32981)
-- Name: workspace_wid_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.workspace_wid_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.workspace_wid_seq OWNER TO postgres;

--
-- TOC entry 4986 (class 0 OID 0)
-- Dependencies: 221
-- Name: workspace_wid_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.workspace_wid_seq OWNED BY public.workspace.wid;


--
-- TOC entry 224 (class 1259 OID 33001)
-- Name: workspacemember; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.workspacemember (
    wmid integer NOT NULL,
    uid integer NOT NULL,
    wid integer NOT NULL,
    invited_at timestamp with time zone,
    joined_at timestamp with time zone,
    role text DEFAULT 'member'::text NOT NULL,
    CONSTRAINT workspacemember_role_check CHECK ((role = ANY (ARRAY['admin'::text, 'member'::text])))
);


ALTER TABLE public.workspacemember OWNER TO postgres;

--
-- TOC entry 223 (class 1259 OID 33000)
-- Name: workspacemember_wmid_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.workspacemember_wmid_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.workspacemember_wmid_seq OWNER TO postgres;

--
-- TOC entry 4987 (class 0 OID 0)
-- Dependencies: 223
-- Name: workspacemember_wmid_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.workspacemember_wmid_seq OWNED BY public.workspacemember.wmid;


--
-- TOC entry 4783 (class 2604 OID 32966)
-- Name: User uid; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public."User" ALTER COLUMN uid SET DEFAULT nextval('public."User_uid_seq"'::regclass);


--
-- TOC entry 4790 (class 2604 OID 33055)
-- Name: channelmember cmid; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.channelmember ALTER COLUMN cmid SET DEFAULT nextval('public.channelmember_cmid_seq'::regclass);


--
-- TOC entry 4791 (class 2604 OID 33080)
-- Name: message mid; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.message ALTER COLUMN mid SET DEFAULT nextval('public.message_mid_seq'::regclass);


--
-- TOC entry 4785 (class 2604 OID 32985)
-- Name: workspace wid; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.workspace ALTER COLUMN wid SET DEFAULT nextval('public.workspace_wid_seq'::regclass);


--
-- TOC entry 4787 (class 2604 OID 33004)
-- Name: workspacemember wmid; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.workspacemember ALTER COLUMN wmid SET DEFAULT nextval('public.workspacemember_wmid_seq'::regclass);


--
-- TOC entry 4799 (class 2606 OID 32978)
-- Name: User User_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public."User"
    ADD CONSTRAINT "User_email_key" UNIQUE (email);


--
-- TOC entry 4801 (class 2606 OID 32976)
-- Name: User User_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public."User"
    ADD CONSTRAINT "User_pkey" PRIMARY KEY (uid);


--
-- TOC entry 4803 (class 2606 OID 32980)
-- Name: User User_username_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public."User"
    ADD CONSTRAINT "User_username_key" UNIQUE (username);


--
-- TOC entry 4811 (class 2606 OID 33040)
-- Name: channel channel_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.channel
    ADD CONSTRAINT channel_pkey PRIMARY KEY (name, wid);


--
-- TOC entry 4813 (class 2606 OID 33063)
-- Name: channelmember channelmember_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.channelmember
    ADD CONSTRAINT channelmember_pkey PRIMARY KEY (cmid);


--
-- TOC entry 4819 (class 2606 OID 33138)
-- Name: message_hidden message_hidden_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.message_hidden
    ADD CONSTRAINT message_hidden_pkey PRIMARY KEY (mid, uid);


--
-- TOC entry 4817 (class 2606 OID 33091)
-- Name: message message_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.message
    ADD CONSTRAINT message_pkey PRIMARY KEY (mid);


--
-- TOC entry 4815 (class 2606 OID 33065)
-- Name: channelmember uq_cm; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.channelmember
    ADD CONSTRAINT uq_cm UNIQUE (wmid, channel_name, channel_wid);


--
-- TOC entry 4807 (class 2606 OID 33016)
-- Name: workspacemember uq_wm; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.workspacemember
    ADD CONSTRAINT uq_wm UNIQUE (uid, wid);


--
-- TOC entry 4805 (class 2606 OID 32994)
-- Name: workspace workspace_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.workspace
    ADD CONSTRAINT workspace_pkey PRIMARY KEY (wid);


--
-- TOC entry 4809 (class 2606 OID 33014)
-- Name: workspacemember workspacemember_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.workspacemember
    ADD CONSTRAINT workspacemember_pkey PRIMARY KEY (wmid);


--
-- TOC entry 4823 (class 2606 OID 33046)
-- Name: channel fk_channel_creator; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.channel
    ADD CONSTRAINT fk_channel_creator FOREIGN KEY (created_by) REFERENCES public."User"(uid) ON DELETE RESTRICT;


--
-- TOC entry 4824 (class 2606 OID 33041)
-- Name: channel fk_channel_workspace; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.channel
    ADD CONSTRAINT fk_channel_workspace FOREIGN KEY (wid) REFERENCES public.workspace(wid) ON DELETE CASCADE;


--
-- TOC entry 4825 (class 2606 OID 33071)
-- Name: channelmember fk_cm_channel; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.channelmember
    ADD CONSTRAINT fk_cm_channel FOREIGN KEY (channel_name, channel_wid) REFERENCES public.channel(name, wid) ON DELETE CASCADE;


--
-- TOC entry 4826 (class 2606 OID 33066)
-- Name: channelmember fk_cm_wm; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.channelmember
    ADD CONSTRAINT fk_cm_wm FOREIGN KEY (wmid) REFERENCES public.workspacemember(wmid) ON DELETE CASCADE;


--
-- TOC entry 4827 (class 2606 OID 33092)
-- Name: message fk_msg_channel; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.message
    ADD CONSTRAINT fk_msg_channel FOREIGN KEY (channel_name, channel_wid) REFERENCES public.channel(name, wid) ON DELETE CASCADE;


--
-- TOC entry 4828 (class 2606 OID 33097)
-- Name: message fk_msg_sender; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.message
    ADD CONSTRAINT fk_msg_sender FOREIGN KEY (cmid) REFERENCES public.channelmember(cmid) ON DELETE CASCADE;


--
-- TOC entry 4821 (class 2606 OID 33017)
-- Name: workspacemember fk_wm_user; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.workspacemember
    ADD CONSTRAINT fk_wm_user FOREIGN KEY (uid) REFERENCES public."User"(uid) ON DELETE CASCADE;


--
-- TOC entry 4822 (class 2606 OID 33022)
-- Name: workspacemember fk_wm_workspace; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.workspacemember
    ADD CONSTRAINT fk_wm_workspace FOREIGN KEY (wid) REFERENCES public.workspace(wid) ON DELETE CASCADE;


--
-- TOC entry 4820 (class 2606 OID 32995)
-- Name: workspace fk_workspace_creator; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.workspace
    ADD CONSTRAINT fk_workspace_creator FOREIGN KEY (created_by) REFERENCES public."User"(uid) ON DELETE RESTRICT;


--
-- TOC entry 4829 (class 2606 OID 33139)
-- Name: message_hidden message_hidden_mid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.message_hidden
    ADD CONSTRAINT message_hidden_mid_fkey FOREIGN KEY (mid) REFERENCES public.message(mid) ON DELETE CASCADE;


--
-- TOC entry 4830 (class 2606 OID 33144)
-- Name: message_hidden message_hidden_uid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.message_hidden
    ADD CONSTRAINT message_hidden_uid_fkey FOREIGN KEY (uid) REFERENCES public."User"(uid) ON DELETE CASCADE;


-- Completed on 2026-04-28 01:24:24

--
-- PostgreSQL database dump complete
--

\unrestrict ocP0aM8tpNfMggAhAxCZhpttFOGvPjDyKeIPgzNZVk4wGWXnz7ybgsMRbESVOpo

