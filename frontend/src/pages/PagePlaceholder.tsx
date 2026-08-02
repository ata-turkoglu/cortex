import { ACard, AInfo } from "../ui/primitives";
export function PagePlaceholder({ title, detail }: { title: string; detail: string }) { return <ACard title={title}><AInfo>{detail} Bu rota Faz 2’de uygulama kabuğuna bağlandı; işlevsel veri kaynağı ilgili backend fazında eklenecek.</AInfo></ACard>; }
