
import java.io.IOException;
import java.net.ServerSocket;

public class Server implements Runnable{
    @Override
    public void run() {
        System.out.println("Server is running");
        try 
        {
        ServerSocket server = new ServerSocket(9999);
    }
    catch (IOException e){
        e.printStackTrace();
        //TODO: handle

    }
    class ConnectionHandler implements Runnable{
        @Override
        public void run(){

        }
    }
}