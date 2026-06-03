'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/store';

export default function RootPage() {
  const { isAuthenticated } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isAuthenticated) {
      router.push('/dashboard');
    } else {
      router.push('/login');
    }
  }, [isAuthenticated, router]);

   return (
     <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900 flex items-center justify-center">
       <div className="text-center text-white">
         {/* CI/CD Banner - TEST */}
         <div className="mb-4 px-4 py-2 bg-green-600/30 border border-green-500/50 rounded-lg inline-block">
           <p className="text-sm text-green-300 font-mono">
             🔧 GitHub Actions CI/CD Active
           </p>
         </div>
         <h1 className="text-4xl font-bold mb-2">EDM ZCO</h1>
         <p className="text-slate-300">Wdrozenie przez GitHub Actions - TEST</p>
       </div>
     </div>
   );
}