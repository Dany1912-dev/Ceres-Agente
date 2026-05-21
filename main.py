from src.ceres_agente import run_agent


def main():
    print("Ceres Agente - escribe 'salir' para terminar\n")
    while True:
        query = input("Tu: ").strip()
        if query.lower() in ("salir", "exit", "quit"):
            break
        if not query:
            continue
        response = run_agent(query)
        print(f"Ceres: {response}\n")


if __name__ == "__main__":
    main()
