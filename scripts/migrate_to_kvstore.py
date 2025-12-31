"""Script para migrar dados do JSON para KVStore (AgentFS).

Migra:
- Whitelist de grupos
- Sessões de grupos existentes
"""

import asyncio
import json
import sys
from pathlib import Path

# Adicionar diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

import app_state
from whatsapp.group_models import GroupQuizSession


async def migrate():
    """Executa migração."""
    print("=" * 60)
    print("MIGRAÇÃO JSON -> KVStore (AgentFS)")
    print("=" * 60)

    # Inicializar AgentFS com sessão fixa para grupos
    print("\n[1] Inicializando AgentFS (sessão: whatsapp-groups-state)...")
    agentfs = await app_state.get_group_agentfs()
    kv = agentfs.kv
    print(f"    ✓ AgentFS inicializado (session: {app_state.GROUP_SESSION_ID})")

    storage_path = Path(".whatsapp_groups")
    migrated_count = 0

    # Migrar whitelist
    print("\n[2] Migrando whitelist...")
    whitelist_file = storage_path / "whitelist.json"
    if whitelist_file.exists():
        try:
            data = json.loads(whitelist_file.read_text())
            groups = data.get("groups", [])
            await kv.set("group:whitelist", {"groups": groups})
            print(f"    ✓ Whitelist migrada: {len(groups)} grupos")
            for g in groups:
                print(f"      - {g}")
        except Exception as e:
            print(f"    ✗ Erro ao migrar whitelist: {e}")
    else:
        print("    - Nenhuma whitelist encontrada")

    # Migrar sessões de grupos
    print("\n[3] Migrando sessões de grupos...")
    for json_file in storage_path.glob("*.json"):
        # Pular whitelist
        if json_file.name == "whitelist.json":
            continue

        try:
            data = json.loads(json_file.read_text())
            group_id = data.get("group_id")

            if not group_id:
                print(f"    - Ignorando {json_file.name} (sem group_id)")
                continue

            # Validar e converter para modelo
            session = GroupQuizSession(**data)

            # Salvar no KVStore
            key = f"group:session:{group_id}"
            await kv.set(key, session.model_dump(mode="json"))

            print(f"    ✓ {json_file.name} -> {key}")
            print(f"      state={session.state}, participants={len(session.participants)}")
            migrated_count += 1

        except Exception as e:
            print(f"    ✗ Erro em {json_file.name}: {e}")

    print("\n" + "=" * 60)
    print(f"MIGRAÇÃO CONCLUÍDA: {migrated_count} sessões migradas")
    print("=" * 60)

    # Verificar dados migrados
    print("\n[4] Verificando dados migrados...")

    whitelist = await kv.get("group:whitelist", default={"groups": []})
    print(f"    Whitelist: {len(whitelist.get('groups', []))} grupos")

    sessions = await kv.list("group:session:")
    print(f"    Sessões: {len(sessions)} grupos")

    for s in sessions:
        print(f"      - {s['key']}: state={s['value'].get('state')}")

    print("\n✅ Migração finalizada!")
    print("\nAgora você pode remover os arquivos JSON antigos se desejar:")
    print(f"  rm -rf {storage_path}/*.json")


if __name__ == "__main__":
    asyncio.run(migrate())
