import React, { useState } from 'react';
import { 
  FolderSearch, MessageSquare, Settings, ShieldCheck, 
  UploadCloud, FileText, Database, LogOut, Send, 
  Paperclip, File, ChevronRight, User, Key, CheckCircle, Clock,
  FolderPlus, Trash2, Shield, Eye, Download, Search, AlertCircle
} from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState('chat');
  const [isAdmin] = useState(true);
  const [chatInput, setChatInput] = useState('');
  const [selectedRawDoc, setSelectedRawDoc] = useState(0);
  
  const rawDocumentsMock = [
    {
      id: 1,
      name: "Zarzadzenie_Dyrektora_nr_5_2026.pdf",
      date: "2026-05-12",
      status: "Przetworzono",
      rawText: `# Zarządzenie nr 5 Dyrektora ZCO z dnia 12 maja 2026 r.

## W sprawie: zasad ewidencji czasu pracy w Zakładzie Radioterapii.

Na podstawie art. 22 ustawy o działalności leczniczej zarządza się, co następuje:

### § 1. Ewidencja Elektroniczna
Wprowadza się bezwzględny obowiązek rejestracji wejść i wyjść przy użyciu kart magnetycznych dla całego personelu medycznego oraz pomocniczego.

### § 2. Normatywy Czasowe i Dyżury
Ewidencja czasu pracy prowadzona na blokach operacyjnych oraz w pracowniach akceleratorów podlega miesięcznemu rozliczeniu przez Kierowników Jednostek.

| Grupa zawodowa | Standardowy wymiar | Maksymalny dyżur | Dodatek radiacyjny |
| :--- | :---: | :---: | :---: |
| Lekarz Radioterapeuta | 7h 35m / doba | 24h | +30% stawki bazowej |
| Fizyk Medyczny | 7h 35m / doba | 12h | +25% stawki bazowej |
| Technik Elektroradiologii | 5h / doba | 12h | +30% stawki bazowej |

### § 3. Przepisy Końcowe
Zarządzenie wchodzi w życie z dniem 1 czerwca 2026 roku.`
    },
    {
      id: 2,
      name: "Ustawa_o_pracowniczych_planach_kapitalowych.docx",
      date: "2026-03-24",
      status: "Przetworzono",
      rawText: `# USTAWA o pracowniczych planach kapitałowych (tekst jednolity)

## Rozdział 1. Przepisy ogólne

### Art. 1. [Zakres regulacji]
Ustawa określa zasady gromadzenia środków w pracowniczych planach kapitałowych, zwanych dalej "PPK", warunki uczestnictwa w PPK oraz zasady wypłaty tych środków.

### Art. 2. [Definicje ustawowe]
1. Osoby zatrudnione - rozumie się przez to pracowników, o których mowa w art. 2 Kodeksu pracy, podlegających obowiązkowo ubezpieczeniom emerytalnemu i rentowym.
2. Podmiot zatrudniający - pracodawca, zleceniodawca.

### Art. 15. [Wpłaty na PPK]
1. Wpłaty na PPK są finansowane przez podmiot zatrudniający oraz przez uczestnika PPK.
2. Wpłata podstawowa finansowana przez uczestnika PPK wynosi 2,0% wynagrodzenia.`
    },
    {
      id: 3,
      name: "Wymogi_Kadrowe_Oddzialy_Onkologiczne.xlsx",
      date: "2026-05-28",
      status: "W trakcie (Docling)",
      rawText: "Trwa generowanie podglądu struktury z pliku Excel..."
    }
  ];

  const NavItem = ({ id, label, icon: Icon, adminOnly = false }) => {
    if (adminOnly && !isAdmin) return null;
    const isActive = activeTab === id || (id === 'admin' && activeTab.startsWith('admin-'));
    return (
      <button
        onClick={() => setActiveTab(id)}
        className={`w-full flex items-center space-x-3 px-4 py-3 rounded-xl transition-all ${
          isActive ? 'bg-blue-600 text-white shadow-md' : 'text-gray-600 hover:bg-gray-100 hover:text-blue-600'
        }`}
      >
        <Icon size={20} />
        <span className="font-medium text-sm">{label}</span>
      </button>
    );
  };

  return (
    <div className="flex h-screen bg-gray-50 font-sans text-gray-800">
      
      {/* 1. BOCZNE MENU (SIDEBAR) */}
      <aside className="w-80 bg-white border-r border-gray-200 flex flex-col shadow-sm z-10 shrink-0">
        <div className="p-6 border-b border-gray-100">
          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 bg-blue-600 rounded-xl flex items-center justify-center text-white font-black text-xl shadow-md">
              Z
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-gray-900">EDM <span className="text-blue-600">ZCO</span></h1>
              <p className="text-xs text-gray-400 font-medium">Z. C. Onkologii w Szczecinie</p>
            </div>
          </div>
        </div>
        
        <nav className="flex-1 p-4 space-y-1.5 overflow-y-auto">
          <p className="px-4 text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">Główne moduły</p>
          <NavItem id="chat" label="Konsultant RAG (Chat)" icon={MessageSquare} />
          <NavItem id="explorer" label="Eksplorator Dokumentów" icon={FolderSearch} />
          
          {isAdmin && (
            <div className="pt-4 mt-4 border-t border-gray-100">
              <p className="px-4 text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">Panel Administratora</p>
              <NavItem id="admin-upload" label="Wgraj Dokumenty" icon={UploadCloud} adminOnly />
              <NavItem id="admin-queue" label="Kolejka Przetwarzania" icon={Database} adminOnly />
              <NavItem id="admin-preview" label="Podgląd RAW (Docling)" icon={FileText} adminOnly />
              <NavItem id="admin-permissions" label="Uprawnienia i Foldery" icon={ShieldCheck} adminOnly />
            </div>
          )}
        </nav>

        <div className="p-4 border-t border-gray-200 bg-gray-50 shrink-0">
          <button 
            onClick={() => setActiveTab('settings')}
            className={`w-full flex items-center space-x-3 p-3 rounded-xl transition-all ${
              activeTab === 'settings' ? 'bg-blue-50 text-blue-700 font-semibold' : 'hover:bg-gray-200'
            }`}
          >
            <div className="h-9 w-9 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold text-sm shrink-0">
              AK
            </div>
            <div className="text-left flex-1 min-w-0">
              <p className="text-sm font-semibold text-gray-800 truncate">Dr Anna Kowalska</p>
              <p className="text-xs text-blue-600 font-medium">Administrator</p>
            </div>
            <Settings size={18} className="text-gray-400 shrink-0" />
          </button>
          <button className="w-full flex items-center space-x-3 px-4 py-2.5 rounded-lg text-red-600 hover:bg-red-50 mt-2 transition-colors text-xs font-semibold">
            <LogOut size={16} />
            <span>Wyloguj się z systemu</span>
          </button>
        </div>
      </aside>

      {/* 2. GŁÓWNY OBSZAR ROBOCZY */}
      <main className="flex-1 flex flex-col min-w-0">
        
        <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-8 shadow-sm shrink-0">
          <div className="flex items-center space-x-3 truncate">
            <span className="text-sm text-gray-400 font-medium">System EDM-RAG</span>
            <ChevronRight size={14} className="text-gray-300" />
            <h2 className="text-base font-semibold text-gray-800 capitalize truncate">
              {activeTab.replace('admin-', 'Zarządzanie: ').replace('chat', 'Inteligentny Asystent RAG').replace('explorer', 'Repozytorium plików').replace('settings', 'Profil i ustawienia')}
            </h2>
          </div>
          <div className="flex items-center space-x-2 bg-green-50 text-green-700 px-3 py-1.5 rounded-full border border-green-200 text-xs font-semibold shrink-0">
            <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse"></span>
            <span className="hidden sm:inline">Połączenie z DGX Spark: Stabilne</span>
          </div>
        </header>

        {/* 3. WIDOKI DYNAMICZNE */}
        <div className="flex-1 overflow-auto p-4 lg:p-8">
          
          {/* CHAT VIEW */}
          {activeTab === 'chat' && (
            <div className="max-w-5xl mx-auto h-full flex flex-col bg-white rounded-2xl shadow-md border border-gray-200 overflow-hidden">
              <div className="flex-1 p-6 overflow-y-auto space-y-6">
                
                <div className="flex justify-start">
                  <div className="bg-gray-100 border border-gray-200 text-gray-800 px-5 py-4 rounded-2xl rounded-tl-sm max-w-2xl shadow-sm text-sm">
                    <p className="font-semibold text-blue-600 mb-1">EDM ZCO RAG-Bot</p>
                    Witaj w wewnętrznym systemie wiedzy Zachodniopomorskiego Centrum Onkologii. 
                    Mogę odpowiedzieć na Twoje pytania w oparciu o zatwierdzone procedury, ustawy, rozporządzenia oraz regulaminy medyczne. Moja wiedza jest ściśle ograniczona do przypisanych Ci praw dostępu. W czym mogę pomóc?
                  </div>
                </div>

                <div className="flex justify-end">
                  <div className="bg-blue-600 text-white px-5 py-3 rounded-2xl rounded-tr-sm max-w-lg shadow-sm text-sm">
                    Jakie są wymagania kadrowe i stawki dyżurów dla technika elektroradiologii w radioterapii?
                  </div>
                </div>

                <div className="flex justify-start">
                  <div className="bg-gray-50 border border-gray-200 text-gray-800 px-6 py-5 rounded-2xl rounded-tl-sm max-w-3xl shadow-sm text-sm space-y-4">
                    <p className="font-semibold text-blue-600">Odpowiedź systemu RAG (Ollama / Llama-3):</p>
                    <p className="leading-relaxed">
                      Dla stanowiska <strong>Technik Elektroradiologii</strong> w Zakładzie Radioterapii, wymiar czasu pracy wynosi <strong>5 godzin na dobę</strong>. Maksymalny czas trwania dyżuru medycznego to <strong>12 godzin</strong>. 
                      Pracownikom na tym stanowisku przysługuje dodatkowo tzw. <strong>dodatek radiacyjny</strong> w wysokości <strong>+30% stawki bazowej</strong>.
                    </p>
                    
                    <div className="pt-4 border-t border-gray-200">
                      <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-3 flex items-center">
                        <FileText size={14} className="mr-1.5 text-blue-500" />
                        Dokumenty źródłowe, na których oparto odpowiedź:
                      </p>
                      <div className="flex flex-wrap gap-2.5">
                        <button className="flex items-center space-x-2 bg-white border border-gray-200 px-3.5 py-2 rounded-xl hover:border-blue-400 hover:text-blue-600 transition-colors shadow-sm text-xs font-medium">
                          <File size={14} className="text-red-500" />
                          <span>Zarzadzenie_Dyrektora_nr_5_2026.pdf</span>
                          <span className="text-[10px] text-gray-400">(Strona 1, § 2)</span>
                          <Download size={12} className="text-gray-400" />
                        </button>
                        <button className="flex items-center space-x-2 bg-white border border-gray-200 px-3.5 py-2 rounded-xl hover:border-blue-400 hover:text-blue-600 transition-colors shadow-sm text-xs font-medium">
                          <File size={14} className="text-blue-500" />
                          <span>Wymogi_Kadrowe_Oddzialy_Onkologiczne.xlsx</span>
                          <span className="text-[10px] text-gray-400">(Wiersz 3, Kolumna D)</span>
                          <Download size={12} className="text-gray-400" />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

              </div>

              <div className="p-4 bg-white border-t border-gray-200">
                <div className="flex items-center bg-gray-50 border border-gray-300 rounded-xl px-4 py-2 focus-within:ring-2 focus-within:ring-blue-500 focus-within:border-transparent transition-all">
                  <button className="p-2 text-gray-400 hover:text-blue-600 transition-colors">
                    <Paperclip size={20} />
                  </button>
                  <input 
                    type="text" 
                    placeholder="Wpisz zapytanie (np. procedury BHP, przepisy PPK)..." 
                    className="flex-1 bg-transparent border-none focus:ring-0 px-4 py-2 text-sm text-gray-700 outline-none w-full min-w-0"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                  />
                  <button className="p-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shadow-sm">
                    <Send size={18} />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* EXPLORER VIEW */}
          {activeTab === 'explorer' && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 h-full flex flex-col">
              <div className="flex flex-col xl:flex-row justify-between items-start xl:items-center gap-4 mb-6 pb-6 border-b border-gray-100">
                <div className="flex flex-wrap items-center text-sm text-gray-500 font-medium">
                  <FolderSearch size={16} className="text-yellow-500 mr-2" />
                  <span className="hover:text-blue-600 cursor-pointer">EDM Główny</span>
                  <ChevronRight size={14} className="mx-2" />
                  <span className="hover:text-blue-600 cursor-pointer">Procedury ZCO</span>
                  <ChevronRight size={14} className="mx-2" />
                  <span className="text-gray-800 font-semibold">Radioterapia i Onkologia</span>
                </div>
                
                <div className="flex items-center bg-gray-50 border border-gray-200 rounded-xl px-3 py-1.5 w-full xl:w-80">
                  <Search size={16} className="text-gray-400 mr-2" />
                  <input type="text" placeholder="Szukaj w tym folderze..." className="bg-transparent border-none text-xs focus:ring-0 outline-none w-full" />
                </div>
              </div>
              
              <div className="space-y-6">
                <div>
                  <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3">Podfoldery (dziedziczące prawa)</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    <div className="flex items-center justify-between p-4 border border-gray-200 rounded-xl hover:border-blue-400 hover:bg-blue-50/50 cursor-pointer transition-all">
                      <div className="flex items-center min-w-0">
                        <FolderPlus className="text-yellow-500 mr-3 shrink-0" size={24} />
                        <div className="truncate">
                          <h4 className="font-semibold text-sm text-gray-800 truncate">Procedury Akceleratorów</h4>
                          <p className="text-xs text-gray-400">8 dokumentów • Pełne dziedziczenie</p>
                        </div>
                      </div>
                      <Shield size={16} className="text-green-500 shrink-0 ml-2" />
                    </div>
                    
                    <div className="flex items-center justify-between p-4 border border-gray-200 rounded-xl hover:border-blue-400 hover:bg-blue-50/50 cursor-pointer transition-all">
                      <div className="flex items-center min-w-0">
                        <FolderPlus className="text-yellow-500 mr-3 shrink-0" size={24} />
                        <div className="truncate">
                          <h4 className="font-semibold text-sm text-gray-800 truncate">Karty Charakterystyki Substancji</h4>
                          <p className="text-xs text-gray-400">3 dokumenty • Dostęp ograniczony</p>
                        </div>
                      </div>
                      <Shield size={16} className="text-amber-500 shrink-0 ml-2" />
                    </div>
                  </div>
                </div>

                <div className="pt-4 border-t border-gray-100">
                  <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3">Pliki w wybranym katalogu</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    <div className="flex items-center justify-between p-4 border border-gray-200 rounded-xl hover:border-blue-400 hover:bg-blue-50/50 cursor-pointer transition-all">
                      <div className="flex items-center min-w-0">
                        <File className="text-red-500 mr-3 shrink-0" size={26} />
                        <div className="truncate">
                          <h4 className="font-semibold text-sm text-gray-800 truncate">Zarzadzenie_Dyrektora_nr_5.pdf</h4>
                          <p className="text-[10px] text-gray-400">PDF • 430 KB • 2026-05-12</p>
                        </div>
                      </div>
                      <div className="flex items-center space-x-1.5 ml-3">
                        <button className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"><Download size={16} /></button>
                      </div>
                    </div>

                    <div className="flex items-center justify-between p-4 border border-gray-200 rounded-xl hover:border-blue-400 hover:bg-blue-50/50 cursor-pointer transition-all">
                      <div className="flex items-center min-w-0">
                        <File className="text-blue-500 mr-3 shrink-0" size={26} />
                        <div className="truncate">
                          <h4 className="font-semibold text-sm text-gray-800 truncate">Ustawa_o_pracowniczych_planach.docx</h4>
                          <p className="text-[10px] text-gray-400">DOCX • 1.2 MB • 2026-03-24</p>
                        </div>
                      </div>
                      <div className="flex items-center space-x-1.5 ml-3">
                        <button className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"><Download size={16} /></button>
                      </div>
                    </div>

                    <div className="flex items-center justify-between p-4 border border-gray-200 rounded-xl hover:border-blue-400 hover:bg-blue-50/50 cursor-pointer transition-all">
                      <div className="flex items-center min-w-0">
                        <File className="text-green-600 mr-3 shrink-0" size={26} />
                        <div className="truncate">
                          <h4 className="font-semibold text-sm text-gray-800 truncate">Wymogi_Kadrowe_Oddzialy.xlsx</h4>
                          <p className="text-[10px] text-gray-400">XLSX • 89 KB • 2026-05-28</p>
                        </div>
                      </div>
                      <div className="flex items-center space-x-1.5 ml-3">
                        <button className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"><Download size={16} /></button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ADMIN: UPLOAD */}
          {activeTab === 'admin-upload' && (
            <div className="max-w-3xl mx-auto bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
              <h3 className="text-lg font-bold text-gray-800 mb-6 flex items-center">
                <UploadCloud size={24} className="text-blue-600 mr-2" />
                Repozytorium Wgrywania Dokumentów
              </h3>
              
              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-2">Wybierz folder docelowy w bazie Postgres:</label>
                  <select 
                    defaultValue="EDM Główny / Procedury ZCO / Radioterapia i Onkologia"
                    className="w-full border border-gray-300 rounded-xl px-4 py-3 bg-gray-50 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                  >
                    <option value="">Wybierz z katalogu drzewiastego...</option>
                    <option value="EDM Główny / Procedury ZCO / Radioterapia i Onkologia">EDM Główny / Procedury ZCO / Radioterapia i Onkologia</option>
                    <option value="EDM Główny / Ustawy krajowe / PPK">EDM Główny / Ustawy krajowe / PPK</option>
                    <option value="EDM Główny / Kadry i Regulaminy / BHP">EDM Główny / Kadry i Regulaminy / BHP</option>
                  </select>
                </div>

                <div className="border-2 border-dashed border-gray-300 hover:border-blue-500 bg-gray-50 hover:bg-blue-50/10 rounded-2xl p-12 text-center cursor-pointer transition-all">
                  <div className="mx-auto w-16 h-16 bg-blue-50 rounded-full flex items-center justify-center mb-4">
                    <UploadCloud size={32} className="text-blue-600" />
                  </div>
                  <h4 className="font-bold text-gray-800 mb-1">Przeciągnij i upuść pliki do wgrania</h4>
                  <p className="text-xs text-gray-500 mb-6">Wspierane formaty: PDF, DOCX, XLSX, PPTX (maksymalnie 50MB/plik)</p>
                  <button className="bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs px-6 py-3 rounded-xl shadow-sm transition-all">
                    Wybierz pliki z dysku Windows
                  </button>
                </div>

                <div className="flex items-center space-x-2 text-xs text-amber-600 bg-amber-50 p-3 rounded-lg border border-amber-200">
                  <AlertCircle size={16} className="shrink-0" />
                  <span>Po wgraniu pliki trafią do kolejki na serwerze DGX, gdzie zostaną automatycznie przeanalizowane przez <strong>Docling</strong> i n8n.</span>
                </div>
              </div>
            </div>
          )}

          {/* ADMIN: QUEUE */}
          {activeTab === 'admin-queue' && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
              <div className="p-6 border-b border-gray-100 flex justify-between items-center bg-gray-50/50">
                <div>
                  <h3 className="font-bold text-gray-800">Statusy kolejkowania zadań n8n + Docling</h3>
                  <p className="text-xs text-gray-500">Monitorowanie procesów ETL w tle na maszynie DGX.</p>
                </div>
                <button className="text-xs font-semibold text-blue-600 hover:text-blue-800">Odśwież tabelę</button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse min-w-[600px]">
                  <thead>
                    <tr className="bg-gray-50 text-gray-600 text-xs border-b border-gray-200 font-bold uppercase tracking-wider">
                      <th className="p-4 pl-6">ID i Nazwa Dokumentu</th>
                      <th className="p-4">Rozmiar</th>
                      <th className="p-4">Przypisany Folder</th>
                      <th className="p-4">Etap przetwarzania</th>
                      <th className="p-4 pr-6 text-center">Chunki</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 text-sm">
                    <tr className="hover:bg-gray-50/50">
                      <td className="p-4 pl-6">
                        <div className="flex items-center space-x-3">
                          <File size={20} className="text-red-500 shrink-0" />
                          <div className="min-w-0">
                            <p className="font-semibold text-gray-800 truncate">Zarzadzenie_nr_5_2026.pdf</p>
                            <p className="text-[10px] text-gray-400">ID: zco_doc_e9a12c</p>
                          </div>
                        </div>
                      </td>
                      <td className="p-4 text-xs text-gray-500 whitespace-nowrap">430 KB</td>
                      <td className="p-4 text-xs text-gray-500 truncate max-w-[150px]">Procedury / Radioterapia</td>
                      <td className="p-4 whitespace-nowrap">
                        <span className="inline-flex items-center space-x-1 bg-green-100 text-green-800 px-2.5 py-1 rounded-md text-xs font-semibold">
                          <CheckCircle size={14} /> <span>Zaindeksowane</span>
                        </span>
                      </td>
                      <td className="p-4 pr-6 text-center font-mono font-bold text-gray-800">14</td>
                    </tr>

                    <tr className="hover:bg-gray-50/50">
                      <td className="p-4 pl-6">
                        <div className="flex items-center space-x-3">
                          <File size={20} className="text-blue-500 shrink-0" />
                          <div className="min-w-0">
                            <p className="font-semibold text-gray-800 truncate">Ustawa_PPK.docx</p>
                            <p className="text-[10px] text-gray-400">ID: zco_doc_ff14b9</p>
                          </div>
                        </div>
                      </td>
                      <td className="p-4 text-xs text-gray-500 whitespace-nowrap">1.2 MB</td>
                      <td className="p-4 text-xs text-gray-500 truncate max-w-[150px]">Ustawy Krajowe / PPK</td>
                      <td className="p-4 whitespace-nowrap">
                        <span className="inline-flex items-center space-x-1 bg-green-100 text-green-800 px-2.5 py-1 rounded-md text-xs font-semibold">
                          <CheckCircle size={14} /> <span>Zaindeksowane</span>
                        </span>
                      </td>
                      <td className="p-4 pr-6 text-center font-mono font-bold text-gray-800">118</td>
                    </tr>

                    <tr className="hover:bg-gray-50/50">
                      <td className="p-4 pl-6">
                        <div className="flex items-center space-x-3">
                          <File size={20} className="text-green-600 shrink-0" />
                          <div className="min-w-0">
                            <p className="font-semibold text-gray-800 truncate">Wymogi_Kadrowe.xlsx</p>
                            <p className="text-[10px] text-gray-400">ID: zco_doc_bb87a2</p>
                          </div>
                        </div>
                      </td>
                      <td className="p-4 text-xs text-gray-500 whitespace-nowrap">89 KB</td>
                      <td className="p-4 text-xs text-gray-500 truncate max-w-[150px]">Procedury / Radioterapia</td>
                      <td className="p-4 whitespace-nowrap">
                        <span className="inline-flex items-center space-x-1.5 bg-yellow-100 text-yellow-800 px-2.5 py-1 rounded-md text-xs font-semibold animate-pulse">
                          <Clock size={14} /> <span>Docling: Detekcja (GPU)</span>
                        </span>
                      </td>
                      <td className="p-4 pr-6 text-center text-gray-400 font-mono">-</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ADMIN: PREVIEW RAW */}
          {activeTab === 'admin-preview' && (
            <div className="flex flex-col lg:flex-row h-full gap-6">
              <div className="w-full lg:w-1/3 bg-white border border-gray-200 rounded-2xl shadow-sm p-4 overflow-y-auto">
                <h3 className="font-bold text-gray-800 mb-4 px-2 text-sm flex items-center justify-between">
                  <span>Lista w PostgreSQL</span>
                  <span className="text-[10px] bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">DB: Documents</span>
                </h3>
                {rawDocumentsMock.map((doc, idx) => (
                  <div 
                    key={doc.id} 
                    onClick={() => setSelectedRawDoc(idx)}
                    className={`p-3.5 rounded-xl mb-2.5 cursor-pointer transition-all border ${
                      selectedRawDoc === idx 
                        ? 'bg-blue-50 border-blue-200 shadow-sm' 
                        : 'hover:bg-gray-50 border-transparent'
                    }`}
                  >
                    <p className="font-semibold text-gray-800 text-xs truncate">{doc.name}</p>
                    <div className="flex justify-between items-center mt-2">
                      <span className="text-[9px] text-gray-400">Dodano: {doc.date}</span>
                      <span className={`text-[9px] px-1.5 py-0.5 rounded-md font-bold ${
                        doc.status.startsWith('Gotowe') || doc.status === 'Przetworzono' 
                          ? 'bg-green-100 text-green-700' 
                          : 'bg-yellow-100 text-yellow-700'
                      }`}>{doc.status}</span>
                    </div>
                  </div>
                ))}
              </div>
              
              <div className="flex-1 bg-gray-900 rounded-2xl shadow-md p-4 lg:p-6 overflow-hidden flex flex-col relative border border-gray-800">
                <h3 className="text-gray-400 text-xs font-mono mb-4 border-b border-gray-800 pb-3 flex flex-col lg:flex-row justify-between items-start lg:items-center gap-2">
                  <div className="flex items-center">
                    <Eye size={14} className="mr-2 text-green-500" />
                    Formatowanie Docling (Markdown)
                  </div>
                  <div className="bg-gray-800 text-gray-300 text-[10px] px-2 py-1 rounded-lg border border-gray-700 font-mono text-center">
                    {"postgres -> documents -> raw_text"}
                  </div>
                </h3>
                
                <div className="flex-1 overflow-y-auto font-mono text-xs text-green-400 leading-relaxed bg-gray-950 p-4 rounded-xl border border-gray-800 whitespace-pre-wrap">
                  {rawDocumentsMock[selectedRawDoc].rawText}
                </div>
              </div>
            </div>
          )}

          {/* ADMIN: PERMISSIONS */}
          {activeTab === 'admin-permissions' && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
              <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6 pb-6 border-b border-gray-100">
                <div>
                  <h3 className="text-lg font-bold text-gray-800">Matryca Uprawnień (RBAC i Foldery)</h3>
                  <p className="text-xs text-gray-500">Zarządzanie bezpieczeństwem RAG: mapowanie ról na drzewo ścieżek.</p>
                </div>
                <button className="bg-blue-600 text-white px-4 py-2.5 rounded-xl text-xs font-semibold hover:bg-blue-700 shadow-sm whitespace-nowrap">
                  + Przypisz Uprawnienie
                </button>
              </div>
              
              <div className="overflow-x-auto">
                <table className="w-full text-left border border-gray-200 rounded-xl min-w-[600px]">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200 text-xs font-bold text-gray-600">
                      <th className="p-3 pl-4">Ścieżka Katalogu</th>
                      <th className="p-3">Użytkownik / Rola</th>
                      <th className="p-3">Stopień dostępu</th>
                      <th className="p-3">Dziedziczenie</th>
                      <th className="p-3 pr-4 text-center">Akcje</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 text-xs text-gray-700">
                    <tr className="hover:bg-gray-50/50">
                      <td className="p-4 pl-4 font-semibold flex items-center min-w-[200px]"><FolderSearch size={16} className="text-yellow-500 mr-2 shrink-0"/> /EDM Główny/Procedury</td>
                      <td className="p-4"><span className="bg-blue-100 text-blue-700 px-2 py-1 rounded-md text-[10px] font-bold">Rola: Personel Medyczny</span></td>
                      <td className="p-4"><span className="text-green-600 font-bold whitespace-nowrap">Odczyt (RAG)</span></td>
                      <td className="p-4 text-gray-500">Tak</td>
                      <td className="p-4 pr-4 text-center">
                        <button className="text-red-500 hover:text-red-700 p-1 rounded hover:bg-red-50"><Trash2 size={16} /></button>
                      </td>
                    </tr>
                    
                    <tr className="hover:bg-gray-50/50">
                      <td className="p-4 pl-4 font-semibold flex items-center min-w-[200px]"><FolderSearch size={16} className="text-yellow-500 mr-2 shrink-0"/> /EDM Główny/Regulaminy</td>
                      <td className="p-4"><span className="bg-gray-100 text-gray-700 px-2 py-1 rounded-md text-[10px] font-bold">Wszyscy pracownicy</span></td>
                      <td className="p-4"><span className="text-green-600 font-bold whitespace-nowrap">Tylko RAG</span></td>
                      <td className="p-4 text-gray-500">Tak</td>
                      <td className="p-4 pr-4 text-center">
                        <button className="text-red-500 hover:text-red-700 p-1 rounded hover:bg-red-50"><Trash2 size={16} /></button>
                      </td>
                    </tr>

                    <tr className="hover:bg-gray-50/50">
                      <td className="p-4 pl-4 font-semibold flex items-center min-w-[200px]"><FolderSearch size={16} className="text-yellow-500 mr-2 shrink-0"/> /EDM Główny/Finanse</td>
                      <td className="p-4"><span className="bg-purple-100 text-purple-700 px-2 py-1 rounded-md text-[10px] font-bold">Rola: Dyrekcja</span></td>
                      <td className="p-4"><span className="text-amber-600 font-bold whitespace-nowrap">Pełen Dostęp</span></td>
                      <td className="p-4 text-gray-500">Nie</td>
                      <td className="p-4 pr-4 text-center">
                        <button className="text-red-500 hover:text-red-700 p-1 rounded hover:bg-red-50"><Trash2 size={16} /></button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* SETTINGS */}
          {activeTab === 'settings' && (
            <div className="max-w-2xl mx-auto bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
              <h3 className="text-lg font-bold text-gray-800 mb-6 flex items-center border-b pb-4">
                <User className="mr-2 text-blue-600" size={22} /> Ustawienia Profilu EDM
              </h3>
              
              <div className="space-y-6">
                <div className="flex items-center space-x-6">
                  <div className="w-20 h-20 rounded-full bg-blue-100 border-2 border-blue-500 shadow-sm flex items-center justify-center text-blue-700 text-2xl font-bold shrink-0">
                    AK
                  </div>
                  <div>
                    <button className="border border-gray-300 bg-white text-gray-700 text-xs font-semibold px-4 py-2.5 rounded-lg hover:bg-gray-50 transition-all">
                      Wgraj nowe zdjęcie
                    </button>
                    <p className="text-[10px] text-gray-400 mt-1">Obsługiwane formaty: JPG, PNG. Maksymalnie 2MB.</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">Imię</label>
                    <input type="text" defaultValue="Anna" className="w-full border border-gray-300 rounded-lg px-3 py-2 bg-gray-50 focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none text-sm" />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">Nazwisko</label>
                    <input type="text" defaultValue="Kowalska" className="w-full border border-gray-300 rounded-lg px-3 py-2 bg-gray-50 focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none text-sm" />
                  </div>
                  <div className="col-span-1 sm:col-span-2">
                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">E-mail służbowy</label>
                    <input type="email" defaultValue="a.kowalska@zco.szczecin.pl" className="w-full border border-gray-300 rounded-lg px-3 py-2 bg-gray-50 focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none text-sm" />
                  </div>
                </div>

                <div className="border-t border-gray-100 pt-6">
                  <h4 className="font-semibold text-gray-800 mb-4 flex items-center text-sm">
                    <Key size={16} className="mr-2 text-gray-500" />
                    Zmiana hasła logowania
                  </h4>
                  <div className="space-y-4 max-w-sm">
                    <input type="password" placeholder="Obecne hasło" className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 outline-none text-sm" />
                    <input type="password" placeholder="Nowe hasło" className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 outline-none text-sm" />
                  </div>
                </div>
                
                <div className="border-t border-gray-100 pt-6 flex justify-end">
                  <button className="bg-blue-600 text-white px-6 py-2.5 rounded-xl text-xs font-semibold hover:bg-blue-700 shadow-md transition-all">
                    Zapisz zmiany profilu
                  </button>
                </div>
              </div>
            </div>
          )}

        </div>
      </main>
    </div>
  );
}