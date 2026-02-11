import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { FileText, FolderOpen, Upload, PanelLeftClose, PanelLeftOpen } from 'lucide-react';

const navItems = [
  { path: '/', label: 'Dashboard', icon: FolderOpen },
  { path: '/exam/new', label: 'New Exam', icon: Upload },
];

function Layout({ children }) {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside
        className={`bg-gray-900 text-white flex flex-col flex-shrink-0 transition-all duration-200 ${
          collapsed ? 'w-16' : 'w-64'
        }`}
      >
        <div className="p-4 border-b border-gray-700 flex items-center justify-between">
          {!collapsed && (
            <div>
              <h1 className="text-xl font-bold flex items-center gap-2">
                <FileText className="w-6 h-6" />
                ExamLens
              </h1>
              <p className="text-xs text-gray-400 mt-1">Anonymous Evaluation</p>
            </div>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className={`p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition-colors ${
              collapsed ? 'mx-auto' : ''
            }`}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? (
              <PanelLeftOpen className="w-5 h-5" />
            ) : (
              <PanelLeftClose className="w-5 h-5" />
            )}
          </button>
        </div>

        <nav className={`flex-1 ${collapsed ? 'px-2 py-4' : 'p-4'}`}>
          <ul className="space-y-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname === item.path;
              return (
                <li key={item.path}>
                  <Link
                    to={item.path}
                    title={collapsed ? item.label : undefined}
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
                      collapsed ? 'justify-center' : ''
                    } ${
                      isActive
                        ? 'bg-blue-600 text-white'
                        : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                    }`}
                  >
                    <Icon className="w-5 h-5 flex-shrink-0" />
                    {!collapsed && item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        {!collapsed && (
          <div className="p-4 border-t border-gray-700 text-xs text-gray-500">
            ExamLens v0.1.0
          </div>
        )}
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto p-6">
        {children}
      </main>
    </div>
  );
}

export default Layout;
