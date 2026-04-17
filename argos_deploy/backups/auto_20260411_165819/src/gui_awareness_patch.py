"""
gui_awareness_patch.py — Патч осознания ARGOS

Исправляет проблему когда GUI не видит все возможности системы:
  • Не отображаются все 35 навыков
  • Не видно 695 компонентов Claude Templates  
  • Нет доступа к 417 агентам
  • Не работает быстрый поиск агентов
"""

import logging
from typing import Dict, List, Optional

log = logging.getLogger("argos.gui.awareness")


def apply_awareness_patch(core):
    """
    Применяет патч осознания к ядру ARGOS.
    Вызывать после создания ArgosCore.
    """
    results = []
    
    # 1. Проверяем skill_loader
    if not hasattr(core, 'skill_loader') or core.skill_loader is None:
        log.error("❌ Skill loader not available")
        return ["Skill loader missing"]
    
    sl = core.skill_loader
    
    # 2. Подсчитываем реальное количество навыков
    pkg_skills = len(sl._original._skills) if hasattr(sl, '_original') else 0
    flat_skills = len(sl._flat_skills) if hasattr(sl, '_flat_skills') else 0
    total_skills = pkg_skills + flat_skills
    
    log.info(f"📦 Package skills: {pkg_skills}")
    log.info(f"📄 Flat skills: {flat_skills}")
    log.info(f"📊 Total skills: {total_skills}")
    results.append(f"✅ Skills: {total_skills} (pkg:{pkg_skills} flat:{flat_skills})")
    
    # 3. Проверяем интегратор
    if hasattr(core, 'integrator') and core.integrator:
        integrator = core.integrator
        
        # Проверяем Claude Templates
        if hasattr(integrator, '_claude_integrator') and integrator._claude_integrator:
            ci = integrator._claude_integrator
            agents = len(ci._agent_cache) if hasattr(ci, '_agent_cache') else 0
            commands = len(ci._command_cache) if hasattr(ci, '_command_cache') else 0
            
            log.info(f"🤖 Claude agents: {agents}")
            log.info(f"⌨️ Claude commands: {commands}")
            results.append(f"✅ Claude: {agents} agents, {commands} commands")
        else:
            log.warning("⚠️ Claude integrator not initialized")
            results.append("⚠️ Claude integrator missing")
    else:
        log.warning("⚠️ Integrator not available")
        results.append("⚠️ Integrator missing")
    
    # 4. Добавляем методы быстрого доступа в core
    _add_awareness_methods(core)
    results.append("✅ Awareness methods added to core")
    
    # 5. Создаем отчет о возможностях
    capabilities = generate_capabilities_report(core)
    core._capabilities_report = capabilities
    
    log.info("\n" + "="*60)
    log.info("ARGOS AWARENESS PATCH APPLIED")
    log.info("="*60)
    for r in results:
        log.info(f"  {r}")
    log.info("="*60)
    
    return results


def _add_awareness_methods(core):
    """Добавляет методы осознания в core."""
    
    def get_all_skills():
        """Возвращает все навыки системы."""
        skills = []
        sl = core.skill_loader
        
        # Package skills
        if hasattr(sl, '_original'):
            for name, skill in sl._original._skills.items():
                skills.append({
                    'name': name,
                    'type': 'package',
                    'version': getattr(skill, 'version', 'unknown'),
                    'description': getattr(skill.manifest, 'description', '') if hasattr(skill, 'manifest') else ''
                })
        
        # Flat skills
        if hasattr(sl, '_flat_skills'):
            for skill in sl._flat_skills:
                skills.append({
                    'name': skill.name,
                    'type': 'flat',
                    'version': skill.version,
                    'description': skill.description,
                    'triggers': skill.triggers
                })
        
        return skills
    
    def get_claude_agents(category: Optional[str] = None):
        """Возвращает агентов Claude Templates."""
        if not (hasattr(core, 'integrator') and 
                hasattr(core.integrator, '_claude_integrator')):
            return []
        
        ci = core.integrator._claude_integrator
        if not hasattr(ci, '_agent_cache'):
            return []
        
        agents = []
        for name, agent in ci._agent_cache.items():
            if category and category.lower() not in agent.category.lower():
                continue
            agents.append({
                'name': name,
                'category': agent.category,
                'description': agent.description[:100] + '...' if len(agent.description) > 100 else agent.description,
                'tools': agent.tools[:5] if agent.tools else []
            })
        
        return agents
    
    def find_claude_agent(task: str):
        """Находит подходящего Claude агента для задачи."""
        if not (hasattr(core, 'integrator') and 
                hasattr(core.integrator, '_claude_integrator')):
            return None
        
        ci = core.integrator._claude_integrator
        agent = ci.find_agent_for_task(task)
        
        if agent:
            return {
                'name': agent.name,
                'category': agent.category,
                'description': agent.description,
                'prompt': agent.content[:500] + '...' if len(agent.content) > 500 else agent.content
            }
        return None
    
    def get_system_stats():
        """Возвращает полную статистику системы."""
        sl = core.skill_loader
        
        stats = {
            'skills': {
                'package': len(sl._original._skills) if hasattr(sl, '_original') else 0,
                'flat': len(sl._flat_skills) if hasattr(sl, '_flat_skills') else 0,
            },
            'claude': {
                'agents': 0,
                'commands': 0,
                'hooks': 0
            },
            'modules': len(core.module_loader.modules) if hasattr(core, 'module_loader') else 0,
            'subsystems': len(core.integrator.list_all()) if hasattr(core, 'integrator') else 0
        }
        
        if hasattr(core, 'integrator') and hasattr(core.integrator, '_claude_integrator'):
            ci = core.integrator._claude_integrator
            stats['claude']['agents'] = len(ci._agent_cache) if hasattr(ci, '_agent_cache') else 0
            stats['claude']['commands'] = len(ci._command_cache) if hasattr(ci, '_command_cache') else 0
        
        stats['skills']['total'] = stats['skills']['package'] + stats['skills']['flat']
        
        return stats
    
    # Добавляем методы
    core.get_all_skills = get_all_skills
    core.get_claude_agents = get_claude_agents
    core.find_claude_agent = find_claude_agent
    core.get_system_stats = get_system_stats


def generate_capabilities_report(core) -> str:
    """Генерирует отчет о всех возможностях."""
    
    lines = [
        "╔" + "═"*58 + "╗",
        "║" + " ARGOS SYSTEM CAPABILITIES ".center(58) + "║",
        "╚" + "═"*58 + "╝",
        "",
    ]
    
    # Skills
    skills = core.get_all_skills() if hasattr(core, 'get_all_skills') else []
    lines.append(f"📦 SKILLS: {len(skills)} total")
    
    pkg = [s for s in skills if s.get('type') == 'package']
    flat = [s for s in skills if s.get('type') == 'flat']
    
    lines.append(f"   Package: {len(pkg)}")
    for s in pkg[:5]:
        lines.append(f"      • {s['name']} v{s['version']}")
    if len(pkg) > 5:
        lines.append(f"      ... and {len(pkg)-5} more")
    
    lines.append(f"   Flat: {len(flat)}")
    for s in flat[:5]:
        lines.append(f"      • {s['name']} ({', '.join(s.get('triggers', [])[:2])})")
    if len(flat) > 5:
        lines.append(f"      ... and {len(flat)-5} more")
    
    lines.append("")
    
    # Claude Templates
    agents = core.get_claude_agents() if hasattr(core, 'get_claude_agents') else []
    lines.append(f"🤖 CLAUDE TEMPLATES: {len(agents)} agents")
    
    from collections import Counter
    cats = Counter(a['category'] for a in agents)
    for cat, count in cats.most_common(5):
        lines.append(f"   • {cat}: {count}")
    
    lines.append("")
    lines.append("Use core.get_all_skills() for all skills")
    lines.append("Use core.get_claude_agents() for all agents")
    lines.append("Use core.find_claude_agent('task') to find agent")
    lines.append("")
    lines.append("═"*60)
    
    return "\n".join(lines)


# Автоприменение при импорте
def auto_apply():
    """Автоматически применяет патч если возможно."""
    try:
        # Пробуем найти существующий core
        import __main__
        if hasattr(__main__, 'core') and __main__.core:
            return apply_awareness_patch(__main__.core)
        
        # Или в глобальном пространстве
        import sys
        for name, obj in sys.modules.items():
            if 'core' in name.lower():
                try:
                    if hasattr(obj, 'skill_loader') and hasattr(obj, 'integrator'):
                        return apply_awareness_patch(obj)
                except:
                    pass
    except Exception as e:
        log.warning(f"Auto-apply failed: {e}")
    
    return None


if __name__ == "__main__":
    print("ARGOS Awareness Patch — Run apply_awareness_patch(core) after ArgosCore()")