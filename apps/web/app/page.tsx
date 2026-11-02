import Link from "next/link";
import { ArrowRight, Files, MessageSquare, Workflow, CheckCircle2 } from "lucide-react";
import { Brand } from "@/components/ui/brand";
import { LinkButton } from "@/components/ui/button";

export default function Home() {
  return <div className="min-h-dvh bg-white">
    <header className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-5"><Brand /><LinkButton href="/login">Open workspace <ArrowRight size={16} /></LinkButton></header>
    <main>
      <section className="pm-grid border-y border-hairline bg-canvas px-6 py-20 md:py-28">
        <div className="mx-auto grid max-w-6xl items-center gap-14 lg:grid-cols-[1.2fr_1fr]">
          <div><p className="mb-6 text-caption font-semibold uppercase tracking-[0.2em] text-primary">Industrial knowledge. Connected.</p><h1 className="max-w-2xl text-5xl font-semibold leading-[1.12] tracking-tight md:text-6xl">Turn plant records into<br /><span className="text-primary">clear next steps.</span></h1><p className="my-7 max-w-xl text-lg leading-relaxed text-muted">Find the evidence behind a change. Ask questions across your project records. Build an investigation your engineers can review.</p><div className="flex flex-wrap gap-3"><LinkButton href="/login">Enter Plant Memory <ArrowRight size={17} /></LinkButton><LinkButton href="#workflow" variant="secondary">Explore the workflow</LinkButton></div><p className="mt-5 text-caption text-muted">A demonstration designed for Spartan Controls. Uses synthetic plant records.</p></div>
          <div className="rounded-2xl border border-hairline bg-white p-7 shadow-[0_20px_60px_#1830470c]">
            <div className="mb-6 flex items-center gap-3 border-b border-hairline pb-5"><div className="rounded-xl bg-primary/10 p-3 text-primary"><Workflow /></div><div><p className="font-semibold">One connected investigation</p><p className="text-caption text-muted">From source document to engineer review</p></div></div>
            {[['01','Collect the records','Equipment lists, drawings and project documents.'],['02','Ask and investigate','Retrieve evidence and trace the impact of a change.'],['03','Review with confidence','Source-linked findings, scope and proposed checks.']].map(([n,title,body])=><div key={n} className="flex gap-4 py-4"><span className="pt-1 text-caption font-semibold text-primary">{n}</span><div><h2 className="font-semibold">{title}</h2><p className="mt-1 text-body text-muted">{body}</p></div></div>)}
            <div className="mt-5 flex items-center gap-2 rounded-lg bg-canvas p-3 text-caption text-muted"><CheckCircle2 size={16} className="text-primary" /> Engineering decisions stay with your team.</div>
          </div>
        </div>
      </section>
      <section id="workflow" className="mx-auto max-w-6xl px-6 py-16"><p className="text-caption uppercase tracking-widest text-muted">Less searching. More understanding.</p><h2 className="mt-3 text-3xl font-semibold">A simpler way to work with plant knowledge.</h2><div className="mt-9 grid gap-8 md:grid-cols-3">{[{icon:Files,title:'Your records, organized',text:'Keep document revisions together and choose exactly which records an investigation uses.'},{icon:MessageSquare,title:'Answers with evidence',text:'Ask about equipment and document conflicts. Open the source behind each cited answer.'},{icon:Workflow,title:'An accountable agent',text:'Follow the investigation steps, review the draft and resolve questions before approving a change.'}].map(({icon:Icon,title,text})=><article key={title}><Icon className="mb-5 text-primary" size={25}/><h3 className="text-title font-semibold">{title}</h3><p className="mt-2 text-body text-muted">{text}</p></article>)}</div></section>
    </main><footer className="border-t border-hairline px-6 py-6 text-center text-caption text-muted">Plant Memory · Independent demonstration · <Link href="/login" className="text-primary">Open workspace</Link></footer>
  </div>;
}
